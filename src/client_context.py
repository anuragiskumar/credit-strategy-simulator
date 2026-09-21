"""The analysis context: which applicants are replayed, and which loans the risk side learns from.

The stakeholder's question was "how does a user choose the dates of the applications they want
to analyse?". There are two windows, and they answer different questions:

  * the APPLICATION window decides who is replayed against the rules. It drives the funnel, the
    approval rate, the decline drivers and every swap set;
  * the PERFORMANCE window decides which booked loans are old enough for their outcome to mean
    anything. Only those feed the bad rate and the PD model.

They are deliberately independent. Recent applications have not had time to go bad, so a bad
rate read off them would flatter whatever window was chosen. The bad rate always comes from
loans that have run the whole performance window, wherever the application window sits — which
is why choosing "last 3 months" cannot make the book look safer.

Cost: the whole file is replayed once per product (about 2.5 seconds on 50,000 applicants) and
every window is a row mask over that replay (see `client_replay.subset`).
"""
from __future__ import annotations

import copy
from collections import OrderedDict
from dataclasses import dataclass

import pandas as pd

from src import client_analysis as A


class ContextError(ValueError):
    """The requested analysis context cannot be analysed. The message says why, in words."""


class WindowError(ContextError):
    """The requested window cannot be analysed."""


class ProductError(ContextError):
    """The requested product is not one the data or the rules carry."""


DESCRIPTIVE = {"id", "name", "label", "context", "applicants", "mature_loans", "mature_booked_from",
               "mature_booked_to"}
"""Fields the engine adds when it reports a window. A screen may send a window back exactly as
it received one (a preset, or the window a result ran on), so these are accepted and ignored."""


@dataclass(frozen=True)
class AnalysisWindow:
    """Application dates, inclusive at both ends, plus the performance window in months.

    `None` for a date means the edge of the data; `None` for `performance_months` means the
    bad definition in config. `resolve()` fills all three in, so a resolved window always says
    exactly what it ran on.
    """
    app_from: pd.Timestamp | None = None
    app_to: pd.Timestamp | None = None
    performance_months: int | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "AnalysisWindow":
        """Parse a request body's `window`. Refuses anything it cannot read, in words."""
        if d is None:
            return cls()
        if not isinstance(d, dict):
            raise WindowError("window must be an object with app_from, app_to and "
                              "performance_months")
        unknown = set(d) - {"app_from", "app_to", "performance_months"} - DESCRIPTIVE
        if unknown:
            raise WindowError(f"window has fields the engine does not know: {sorted(unknown)}")

        def date(key):
            v = d.get(key)
            if v in (None, ""):
                return None
            try:
                return pd.Timestamp(v).normalize()
            except (TypeError, ValueError):
                raise WindowError(f"window.{key} {v!r} is not a date (use YYYY-MM-DD)") from None

        months = d.get("performance_months")
        if months not in (None, ""):
            try:
                months = int(months)
            except (TypeError, ValueError):
                raise WindowError(f"window.performance_months {months!r} is not a whole "
                                  "number of months") from None
            if months <= 0:
                raise WindowError("window.performance_months must be at least one month")
        else:
            months = None
        return cls(app_from=date("app_from"), app_to=date("app_to"), performance_months=months)

    @property
    def key(self) -> tuple:
        return (self.app_from, self.app_to, self.performance_months)

    @property
    def label(self) -> str:
        if self.app_from is None or self.app_to is None:
            return "all applications"
        same_year = self.app_from.year == self.app_to.year
        left = self.app_from.strftime("%-d %b" if same_year else "%-d %b %Y")
        return f"{left} – {self.app_to.strftime('%-d %b %Y')}"

    def to_dict(self) -> dict:
        def iso(t):
            return None if t is None else t.strftime("%Y-%m-%d")
        return {"app_from": iso(self.app_from), "app_to": iso(self.app_to),
                "performance_months": self.performance_months, "label": self.label}


def data_range(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    dates = pd.to_datetime(df["app_date"]).dt.normalize()
    return dates.min(), dates.max()


def default_window(df: pd.DataFrame, cfg: dict) -> AnalysisWindow:
    """The configured default: the last N months of applications in the file."""
    months = int(cfg["analysis"]["default_window"]["last_months"])
    return last_months(df, cfg, months)


def last_months(df: pd.DataFrame, cfg: dict, months: int) -> AnalysisWindow:
    _, hi = data_range(df)
    lo = hi - pd.DateOffset(months=months) + pd.Timedelta(days=1)
    return resolve(AnalysisWindow(app_from=lo, app_to=hi), df, cfg)


def resolve(window: AnalysisWindow | None, df: pd.DataFrame, cfg: dict) -> AnalysisWindow:
    """Fill in the edges of the data and the configured performance window; check the dates."""
    window = window or AnalysisWindow()
    lo, hi = data_range(df)
    app_from = window.app_from if window.app_from is not None else lo
    app_to = window.app_to if window.app_to is not None else hi
    if app_to < lo or app_from > hi:
        raise WindowError(f"no applications in {app_from:%-d %b %Y} – {app_to:%-d %b %Y}: the "
                          f"data covers {lo:%-d %b %Y} – {hi:%-d %b %Y}")
    if app_from > app_to:
        raise WindowError(f"the window starts on {app_from:%-d %b %Y}, after it ends on "
                          f"{app_to:%-d %b %Y}")
    months = window.performance_months or A.bad_definition(cfg)["within_months"]
    return AnalysisWindow(app_from=app_from, app_to=app_to, performance_months=int(months))


def app_mask(df: pd.DataFrame, window: AnalysisWindow) -> pd.Series:
    """Applications dated inside the window, both ends inclusive, by calendar day."""
    dates = pd.to_datetime(df["app_date"]).dt.normalize()
    return (dates >= window.app_from) & (dates <= window.app_to)


def cfg_for(cfg: dict, window: AnalysisWindow) -> dict:
    """Config with the bad definition set to this window's performance months.

    A loan is judged over `performance_months`, and is mature only once it has run that long:
    one number, so the two can never disagree.
    """
    out = copy.deepcopy(cfg)
    out["outcome"]["bad_definition"]["within_months"] = int(window.performance_months)
    return out


def check(window: AnalysisWindow, n_applicants: int, n_mature: int, cfg: dict) -> None:
    """Refuse a window too thin to say anything, the same way a locked rule is refused."""
    an = cfg["analysis"]
    if n_applicants == 0:
        raise WindowError(f"no applications in {window.label}")
    if n_applicants < an["min_applicants"]:
        raise WindowError(f"only {n_applicants:,} applications in {window.label}; at least "
                          f"{an['min_applicants']:,} are needed for rates worth acting on. "
                          "Widen the window.")
    need = int(cfg["risk_model"]["min_training_rows"])
    if n_mature < need:
        raise WindowError(
            f"only {n_mature:,} booked loans have run a {window.performance_months}-month "
            f"performance window by the extract date; at least {need:,} are needed to judge "
            "risk. Shorten the performance window.")


class ContextCache:
    """Baselines per analysis context (product and window), on one replay per product.

    The replay is the expensive part and depends only on the product. The outcome and the PD
    model depend on the performance window; everything else is a row mask. Only recent
    baselines are kept, so a person flicking between presets never waits twice.
    """

    def __init__(self, df: pd.DataFrame, inv, cfg: dict, *, size: int | None = None):
        self.df, self.inv, self.cfg = df, inv, cfg
        self.size = int(size or cfg["analysis"]["cached_contexts"])
        self._full: dict[str, object] = {}
        self._perf: dict[tuple, tuple] = {}
        self._baselines: OrderedDict = OrderedDict()

    # ------------------------------------------------------------------ products
    def products(self) -> list[str]:
        """The products the selector offers: configured, and present in the data."""
        present = set(self.df["product"].dropna().unique())
        offered = self.cfg.get("products") or [self.cfg["product"]]
        return [p for p in offered if p in present]

    def product(self, product: str | None = None) -> str:
        p = product or self.cfg["product"]
        if p not in self.products():
            known = ", ".join(self.products()) or "none"
            raise ProductError(f"no {p} applications to analyse; the data carries {known}")
        return p

    def cfg_for_product(self, product: str | None = None) -> dict:
        return {**self.cfg, "product": self.product(product)}

    def product_df(self, product: str | None = None) -> pd.DataFrame:
        return self.full(product).df

    # ------------------------------------------------------------------ baselines
    def full(self, product: str | None = None):
        from src import client_simulate as S
        p = self.product(product)
        if p not in self._full:
            self._full[p] = S.full_replay(self.df, self.inv, self.cfg_for_product(p))
        return self._full[p]

    def default(self, product: str | None = None) -> AnalysisWindow:
        return default_window(self.product_df(product), self.cfg)

    def resolve(self, window: AnalysisWindow | None, product: str | None = None) -> AnalysisWindow:
        return resolve(window or self.default(product), self.product_df(product), self.cfg)

    def baseline(self, window: AnalysisWindow | None = None, product: str | None = None):
        from src import client_simulate as S
        p = self.product(product)
        w = self.resolve(window, p)
        key = (p, w.key)
        if key in self._baselines:
            self._baselines.move_to_end(key)
            return self._baselines[key]
        base = S.build_baseline(self.df, self.inv, self.cfg_for_product(p), window=w,
                                full=self.full(p), perf_cache=self._perf)
        self._baselines[key] = base
        while len(self._baselines) > self.size:
            self._baselines.popitem(last=False)
        return base
