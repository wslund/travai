"""Feature engineering för TravAI.

Bygger en materialiserad feature-tabell från transaktionsdata. Designprincipen
är "leak-fri": för varje start räknar vi bara features som var kända FÖRE
den startens lopp - aldrig efter.

Storlek: med 810k starts blir DataFrame ~250-400 MB i minne. Hanterbart.

Användning:
    from travai.features import FeatureBuilder
    builder = FeatureBuilder()
    df = builder.build_all()  # returnerar features-DataFrame
    builder.write(df)         # skriver till features.start_features
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from travai.db import engine as default_engine
from travai.logging_setup import get_logger

logger = get_logger(__name__)


# SQL-frågan som läser in all data vi behöver för feature engineering.
# Vi joinar starts -> races -> meetings -> horses -> persons så vi har allt
# i en bred DataFrame. Filter på finish_position IS NOT NULL för att hoppa
# över scratched/DNF-starter där vi inte har riktig data.
BASE_DATA_SQL = """
SELECT
    s.id AS start_id,
    s.race_id,
    s.horse_id,
    s.rider_id,
    s.trainer_id,
    s.start_number,
    s.post_position,
    s.horse_age_at_start,
    s.distance_m AS start_distance_m,
    s.finish_position,
    s.km_time_s,
    s.prize_money_minor,
    s.final_win_odds,
    s.sulky_changed,
    s.shoes_front,
    s.shoes_back,
    s.shoes_front_changed,
    s.shoes_back_changed,
    r.distance_m AS race_distance_m,
    r.scheduled_start_time,
    r.actual_start_time,
    m.track_id,
    m.date AS race_date,
    h.father_id,
    h.mother_id
FROM starts s
JOIN races r ON r.id = s.race_id
JOIN meetings m ON m.id = r.meeting_id
JOIN horses h ON h.id = s.horse_id
WHERE s.finish_position IS NOT NULL
"""


# Odds från V75-poolen (om sådan finns) - en separat query för att inte
# duplicera starts-raderna.
V75_POOL_SQL = """
SELECT
    o.start_id,
    o.pool_share AS v75_pool_share
FROM odds_snapshots o
WHERE o.bet_type_code = 'V75'
  AND o.pool_share IS NOT NULL
"""


class FeatureBuilder:
    """Bygger features-DataFrames från transaktionsdata."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or default_engine

    # ---------- Huvudflöde ----------

    def build_all(self, limit: int | None = None) -> pd.DataFrame:
        """Bygger den kompletta features-DataFrame:n.

        limit: om satt, ta bara N rader från start (för test/utveckling).
        """
        logger.info("feature_build_start")

        df = self._load_base_data(limit=limit)
        logger.info("loaded_base_data", rows=len(df))

        df = self._add_v75_pool(df)
        logger.info("added_v75_pool")

        df = self._sort_for_temporal_features(df)
        df = self._add_horse_features(df)
        logger.info("added_horse_features")

        df = self._add_rider_features(df)
        logger.info("added_rider_features")

        df = self._add_trainer_features(df)
        logger.info("added_trainer_features")

        df = self._add_pedigree_features(df)
        logger.info("added_pedigree_features")

        df = self._add_race_context_features(df)
        logger.info("added_race_context")

        df = self._add_odds_features(df)
        logger.info("added_odds_features")

        df = self._add_time_features(df)
        logger.info("added_time_features")

        df = self._add_target(df)
        logger.info("added_target", rows=len(df))

        df = self._select_output_columns(df)
        logger.info("feature_build_done", rows=len(df), columns=len(df.columns))
        return df

    def write(
        self, df: pd.DataFrame, schema: str = "features", table: str = "start_features"
    ) -> None:
        """Skriv features-DataFrame till databasen. Skriver över befintlig data."""
        logger.info("writing_features", rows=len(df), table=f"{schema}.{table}")
        # Vi använder pandas to_sql med method='multi' för batchade inserts
        # Truncate först eftersom vi bygger om allt från grunden
        with self.engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {schema}.{table}"))
        df.to_sql(
            table,
            self.engine,
            schema=schema,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=5000,
        )
        logger.info("write_done")

    # ---------- Steg-för-steg ----------

    def _load_base_data(self, limit: int | None = None) -> pd.DataFrame:
        sql = BASE_DATA_SQL
        if limit:
            sql += f"\nORDER BY s.id LIMIT {limit}"
        df = pd.read_sql(
            sql,
            self.engine,
            parse_dates=["scheduled_start_time", "actual_start_time", "race_date"],
        )
        # Använd race_date som primär tidsstämpel för rolling features
        # (scheduled_start_time kan saknas för gamla lopp)
        df["effective_date"] = df["race_date"]
        # Numeric-kolumner: lite typ-konvertering
        df["km_time_s"] = pd.to_numeric(df["km_time_s"], errors="coerce")
        df["final_win_odds"] = pd.to_numeric(df["final_win_odds"], errors="coerce")
        return df

    def _add_v75_pool(self, df: pd.DataFrame) -> pd.DataFrame:
        v75 = pd.read_sql(V75_POOL_SQL, self.engine)
        # Det kan finnas flera snapshots per start - ta sista (final)
        v75 = v75.drop_duplicates(subset=["start_id"], keep="last")
        v75["v75_pool_share"] = pd.to_numeric(v75["v75_pool_share"], errors="coerce")
        return df.merge(v75, on="start_id", how="left")

    def _sort_for_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.sort_values(["horse_id", "effective_date"]).reset_index(drop=True)

    # ---------- Häst-features ----------

    def _add_horse_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Karriär + rullande features per häst.

        Alla features använder .shift(1) för att exkludera nuvarande rad
        (= rensa data leakage).
        """
        g = df.groupby("horse_id", sort=False)

        # Career counters (prior to this race)
        df["career_starts_prior"] = g.cumcount()
        df["career_wins_prior"] = (
            g["finish_position"].transform(lambda x: (x == 1).cumsum().shift(1).fillna(0))
        ).astype("int64")
        df["career_top3_prior"] = (
            g["finish_position"].transform(lambda x: (x <= 3).cumsum().shift(1).fillna(0))
        ).astype("int64")
        df["career_earnings_minor_prior"] = (
            g["prize_money_minor"]
            .transform(lambda x: x.cumsum().shift(1).fillna(0))
            .astype("int64")
        )

        # Career rates (NaN vid 0 starts för att undvika 0/0)
        df["career_win_rate"] = np.where(
            df["career_starts_prior"] > 0,
            df["career_wins_prior"] / df["career_starts_prior"],
            np.nan,
        )
        df["career_top3_rate"] = np.where(
            df["career_starts_prior"] > 0,
            df["career_top3_prior"] / df["career_starts_prior"],
            np.nan,
        )

        # Dagar sedan senaste start
        df["days_since_last_start"] = g["effective_date"].diff().dt.days

        # Rolling time-based features (30d, 90d, 365d)
        df = self._add_time_window_features(df, "horse_id")

        # Best km-time career & 90d
        df["best_km_time_career"] = g["km_time_s"].transform(lambda x: x.shift(1).expanding().min())
        df["best_km_time_90d"] = self._time_window_min(df, "horse_id", "km_time_s", days=90)

        # Rolling form (5 last starts)
        df["avg_finish_pos_last5"] = g["finish_position"].transform(
            lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
        )
        df["avg_km_time_last5"] = g["km_time_s"].transform(
            lambda x: x.shift(1).rolling(window=5, min_periods=1).mean()
        )

        # Bana- och distansspecifika
        df["starts_at_track_prior"] = self._cumulative_match_prior(df, "horse_id", "track_id")
        df["wins_at_track_prior"] = self._cumulative_match_prior_filtered(
            df, "horse_id", "track_id", df["finish_position"] == 1
        )
        df["starts_at_distance_prior"] = self._cumulative_distance_match_prior(df)

        return df

    def _add_time_window_features(self, df: pd.DataFrame, group_col: str) -> pd.DataFrame:
        """Lägg till starts/wins/top3 över 30/90/365 dagars rullande fönster."""
        for days in [30, 90, 365]:
            df[f"starts_{days}d"] = self._time_window_count(df, group_col, days)
            df[f"wins_{days}d"] = self._time_window_count_filtered(
                df, group_col, days, df["finish_position"] == 1
            )
            if days in (30, 90):
                df[f"top3_{days}d"] = self._time_window_count_filtered(
                    df, group_col, days, df["finish_position"] <= 3
                )
        return df

    # ---------- Time-window helpers (effektiva implementationer) ----------

    def _time_window_count(self, df: pd.DataFrame, group_col: str, days: int) -> pd.Series:
        """Antal rader per group inom 'days' bakåt, EXKLUSIVE nuvarande."""
        result = pd.Series(0, index=df.index, dtype="int64")
        for _gid, idx in df.groupby(group_col, sort=False).groups.items():
            dates = df.loc[idx, "effective_date"]
            # För varje rad: hur många tidigare rader hade datum >= (now - days)?
            # Sortera redan via _sort_for_temporal_features
            result.loc[idx] = self._count_in_window(dates.values, days)
        return result

    def _time_window_count_filtered(
        self, df: pd.DataFrame, group_col: str, days: int, mask: pd.Series
    ) -> pd.Series:
        """Antal rader per group inom 'days' bakåt där mask=True, exklusive nuvarande."""
        result = pd.Series(0, index=df.index, dtype="int64")
        for _gid, idx in df.groupby(group_col, sort=False).groups.items():
            dates = df.loc[idx, "effective_date"].values
            flags = mask.loc[idx].fillna(False).astype(bool).values
            result.loc[idx] = self._count_in_window_filtered(dates, flags, days)
        return result

    def _time_window_min(
        self, df: pd.DataFrame, group_col: str, value_col: str, days: int
    ) -> pd.Series:
        """Min-värde av value_col per group inom 'days' bakåt, exklusive nuvarande."""
        result = pd.Series(np.nan, index=df.index, dtype="float64")
        for _gid, idx in df.groupby(group_col, sort=False).groups.items():
            dates = df.loc[idx, "effective_date"].values
            vals = df.loc[idx, value_col].values.astype("float64")
            result.loc[idx] = self._min_in_window(dates, vals, days)
        return result

    @staticmethod
    def _count_in_window(dates: np.ndarray, days: int) -> np.ndarray:
        """För varje datum i sorterad array: räkna hur många tidigare datum
        låg inom 'days' bakåt. Använd two-pointer för O(n)."""
        n = len(dates)
        out = np.zeros(n, dtype="int64")
        left = 0
        ns_per_day = np.timedelta64(days, "D")
        for i in range(n):
            cutoff = dates[i] - ns_per_day
            while left < i and dates[left] < cutoff:
                left += 1
            out[i] = i - left
        return out

    @staticmethod
    def _count_in_window_filtered(dates: np.ndarray, flags: np.ndarray, days: int) -> np.ndarray:
        """Som ovan men räkna bara där flag=True."""
        n = len(dates)
        out = np.zeros(n, dtype="int64")
        left = 0
        running = 0
        ns_per_day = np.timedelta64(days, "D")
        for i in range(n):
            cutoff = dates[i] - ns_per_day
            while left < i and dates[left] < cutoff:
                if flags[left]:
                    running -= 1
                left += 1
            out[i] = running
            if flags[i]:
                running += 1
        return out

    @staticmethod
    def _min_in_window(dates: np.ndarray, vals: np.ndarray, days: int) -> np.ndarray:
        """Min-värde i window. O(n²) i värsta fall, men sliding window ger amortiserat O(n)."""
        n = len(dates)
        out = np.full(n, np.nan, dtype="float64")
        ns_per_day = np.timedelta64(days, "D")
        for i in range(n):
            cutoff = dates[i] - ns_per_day
            window_min = np.nan
            for j in range(i - 1, -1, -1):
                if dates[j] < cutoff:
                    break
                v = vals[j]
                if not np.isnan(v) and (np.isnan(window_min) or v < window_min):
                    window_min = v
            out[i] = window_min
        return out

    def _cumulative_match_prior(
        self, df: pd.DataFrame, group_col: str, match_col: str
    ) -> pd.Series:
        """Räkna tidigare rader i samma grupp som har samma värde i match_col."""
        # Vi gör detta via en counter: för varje (horse_id, track_id) håller vi
        # en löpande räknare som ökar för varje rad, men shiftas så att
        # nuvarande rad ej räknas.
        df_sorted = df.sort_values([group_col, match_col, "effective_date"])
        cnt = df_sorted.groupby([group_col, match_col], sort=False).cumcount()
        # Mappa tillbaka till ursprungsordning
        return cnt.reindex(df.index).astype("int64")

    def _cumulative_match_prior_filtered(
        self,
        df: pd.DataFrame,
        group_col: str,
        match_col: str,
        mask: pd.Series,
    ) -> pd.Series:
        """Räkna tidigare rader i (group, match) där mask=True."""
        df_sorted = df.sort_values([group_col, match_col, "effective_date"]).copy()
        df_sorted["_mask_int"] = mask.reindex(df_sorted.index).fillna(False).astype(int)
        df_sorted["_cum"] = (
            df_sorted.groupby([group_col, match_col], sort=False)["_mask_int"]
            .cumsum()
            .shift(1)
            .fillna(0)
        )
        # Edge case: shift hopper över första raden i varje grupp
        first_in_group = df_sorted.groupby([group_col, match_col], sort=False).cumcount() == 0
        df_sorted.loc[first_in_group, "_cum"] = 0
        return df_sorted["_cum"].reindex(df.index).astype("int64")

    def _cumulative_distance_match_prior(self, df: pd.DataFrame) -> pd.Series:
        """Räkna tidigare starter inom +-200m av denna start."""
        out = pd.Series(0, index=df.index, dtype="int64")
        for _gid, idx in df.groupby("horse_id", sort=False).groups.items():
            distances = df.loc[idx, "race_distance_m"].values.astype("float64")
            n = len(distances)
            for i in range(n):
                if np.isnan(distances[i]):
                    continue
                # Räkna tidigare rader med distance inom +-200m
                cnt = 0
                for j in range(i):
                    d = distances[j]
                    if not np.isnan(d) and abs(d - distances[i]) <= 200:
                        cnt += 1
                out.loc[idx[i]] = cnt
        return out

    # ---------- Kusk / Tränare ----------

    def _add_rider_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._add_person_role_features(df, "rider_id", prefix="rider")

    def _add_trainer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return self._add_person_role_features(df, "trainer_id", prefix="trainer")

    def _add_person_role_features(
        self, df: pd.DataFrame, role_col: str, prefix: str
    ) -> pd.DataFrame:
        """Rullande drives/wins för en kusk eller tränare.

        OBS: vi sorterar tillfälligt om för person men behåller index så vi
        kan mappa tillbaka.
        """
        # Sortera per person + datum, beräkna rolling
        df_sorted = df.sort_values([role_col, "effective_date"], kind="stable")
        groups = df_sorted.groupby(role_col, sort=False, dropna=True)

        for days in [30, 90]:
            col_drives = (
                f"{prefix}_drives_{days}d" if prefix == "rider" else f"{prefix}_starts_{days}d"
            )
            col_wins = f"{prefix}_wins_{days}d"
            df_sorted[col_drives] = 0
            df_sorted[col_wins] = 0

            for _person_id, idx in groups.groups.items():
                dates = df_sorted.loc[idx, "effective_date"].values
                wins_flag = (
                    (df_sorted.loc[idx, "finish_position"] == 1).fillna(False).astype(bool).values
                )
                df_sorted.loc[idx, col_drives] = self._count_in_window(dates, days)
                df_sorted.loc[idx, col_wins] = self._count_in_window_filtered(
                    dates, wins_flag, days
                )

        # Win rate (90d)
        col_drives_90 = f"{prefix}_drives_90d" if prefix == "rider" else f"{prefix}_starts_90d"
        df_sorted[f"{prefix}_win_rate_90d"] = np.where(
            df_sorted[col_drives_90] > 0,
            df_sorted[f"{prefix}_wins_90d"] / df_sorted[col_drives_90],
            np.nan,
        )

        # Mappa tillbaka
        return df_sorted.sort_index()

    # ---------- Pedigree ----------

    def _add_pedigree_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """För varje förälder: totalt antal segrar bland avkomman i datan.

        OBS: detta är inte tidsmedvetet - vi använder hela dataset. För strikt
        tidsmedvetenhet hade vi behövt rolling sum av segrar för avkomman
        upp till race_date. Förenklat för v1.
        """
        # Segrar per häst
        wins_per_horse = (df[df["finish_position"] == 1].groupby("horse_id").size()).rename("wins")

        # För varje far/mor: summa segrar av alla avkomman
        father_wins = (
            df[["horse_id", "father_id"]]
            .drop_duplicates()
            .merge(wins_per_horse, left_on="horse_id", right_index=True, how="left")
            .groupby("father_id")["wins"]
            .sum()
        ).rename("father_offspring_wins")

        mother_wins = (
            df[["horse_id", "mother_id"]]
            .drop_duplicates()
            .merge(wins_per_horse, left_on="horse_id", right_index=True, how="left")
            .groupby("mother_id")["wins"]
            .sum()
        ).rename("mother_offspring_wins")

        df = df.merge(father_wins, left_on="father_id", right_index=True, how="left")
        df = df.merge(mother_wins, left_on="mother_id", right_index=True, how="left")
        df["father_offspring_wins"] = df["father_offspring_wins"].fillna(0).astype("int64")
        df["mother_offspring_wins"] = df["mother_offspring_wins"].fillna(0).astype("int64")
        return df

    # ---------- Race-kontext ----------

    def _add_race_context_features(self, df: pd.DataFrame) -> pd.DataFrame:
        # Antal startande per lopp
        df["num_starters"] = df.groupby("race_id")["start_id"].transform("count")
        # Normaliserad post-position
        df["post_position_normalized"] = np.where(
            df["num_starters"] > 0,
            df["post_position"] / df["num_starters"],
            np.nan,
        )
        # Utrustning
        df["shoes_either_changed"] = df["shoes_front_changed"].fillna(False) | df[
            "shoes_back_changed"
        ].fillna(False)
        # Använd race_distance_m som "distance_m" om start_distance_m är NaN
        df["distance_m"] = df["start_distance_m"].fillna(df["race_distance_m"])
        return df

    # ---------- Odds ----------

    def _add_odds_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df["log_final_win_odds"] = df["final_win_odds"].apply(
            lambda x: math.log(float(x)) if x is not None and not pd.isna(x) and x > 0 else np.nan
        )
        # Rank inom lopp - lägst odds = favorit (rank 1)
        df["odds_rank_in_race"] = df.groupby("race_id")["final_win_odds"].rank(
            method="min", na_option="bottom"
        )
        df["is_favorite"] = df["odds_rank_in_race"] == 1
        return df

    # ---------- Tid ----------

    def _add_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df["month"] = df["effective_date"].dt.month
        df["day_of_week"] = df["effective_date"].dt.dayofweek
        df["year"] = df["effective_date"].dt.year
        return df

    # ---------- Target ----------

    def _add_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """Sätt relevance_score för LambdaRank.

        relevance = max(0, num_starters - finish_position + 1)
        Vinnare: high score, DNF/disq: 0.
        """
        df["relevance_score"] = np.where(
            (df["finish_position"].notna()) & (df["finish_position"] > 0),
            np.maximum(0, df["num_starters"] - df["finish_position"] + 1),
            0,
        ).astype("int64")
        return df

    # ---------- Output-kolumner ----------

    def _select_output_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Plocka ut bara de kolumner som matchar StartFeatures-modellen."""
        cols = [
            "start_id",
            "race_id",
            "horse_id",
            "race_date",
            # Target
            "finish_position",
            "relevance_score",
            # Häst-career
            "career_starts_prior",
            "career_wins_prior",
            "career_top3_prior",
            "career_earnings_minor_prior",
            "career_win_rate",
            "career_top3_rate",
            # Häst-rolling
            "starts_30d",
            "starts_90d",
            "starts_365d",
            "wins_30d",
            "wins_90d",
            "wins_365d",
            "top3_30d",
            "top3_90d",
            # Häst-tider
            "avg_finish_pos_last5",
            "best_km_time_career",
            "best_km_time_90d",
            "avg_km_time_last5",
            # Vila
            "days_since_last_start",
            # Häst-bana/distans
            "starts_at_track_prior",
            "wins_at_track_prior",
            "starts_at_distance_prior",
            # Rider
            "rider_drives_30d",
            "rider_wins_30d",
            "rider_drives_90d",
            "rider_wins_90d",
            "rider_win_rate_90d",
            # Trainer
            "trainer_starts_30d",
            "trainer_wins_30d",
            "trainer_starts_90d",
            "trainer_wins_90d",
            "trainer_win_rate_90d",
            # Pedigree
            "father_offspring_wins",
            "mother_offspring_wins",
            # Equipment
            "shoes_front",
            "shoes_back",
            "shoes_either_changed",
            "sulky_changed",
            # Race-context
            "num_starters",
            "post_position",
            "post_position_normalized",
            "horse_age_at_start",
            "distance_m",
            # Odds
            "final_win_odds",
            "log_final_win_odds",
            "odds_rank_in_race",
            "is_favorite",
            "v75_pool_share",
            # Tid
            "month",
            "day_of_week",
            "year",
        ]
        # Behåll bara kolumner som faktiskt finns (defensiv mot framtida ändringar)
        existing = [c for c in cols if c in df.columns]
        return df[existing].copy()


def chunked(seq: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
