"""Patch som ersätter _add_pedigree_features i builder.py med time-aware version.

Kör detta från projektets rotmapp:
    python3 scripts/patch_pedigree_time_aware.py
"""

import re
from pathlib import Path

BUILDER_PATH = Path("src/travai/features/builder.py")

NEW_FUNCTION = '''    def _add_pedigree_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Tidsmedvetna pedigree-features (fixad i steg 5d).

        För varje start: antalet vinster av syskon (samma mother_id/father_id)
        som inträffade STRIKT FÖRE start.race_date.

        Använder pandas merge_asof med direction='backward' och
        allow_exact_matches=False -> O((n+m) log) prestanda.

        Original-bug (pre-5d): räknade total summa av alla syskons vinster
        över hela dataset, vilket gav future leakage.
        """
        original_index = df.index.copy()
        df = df.copy()

        # Steg 1: hitta alla vinster med föräldrar
        wins_df = df.loc[
            df["finish_position"] == 1,
            ["race_date", "horse_id", "mother_id", "father_id"],
        ].copy()

        # Steg 2: cumcount per mor (sorterat per datum)
        mother_wins = (
            wins_df[wins_df["mother_id"].notna()]
            .sort_values(["mother_id", "race_date"])
            .reset_index(drop=True)
        )
        mother_wins["mother_offspring_wins"] = (
            mother_wins.groupby("mother_id").cumcount() + 1
        )
        mother_lookup = mother_wins[
            ["race_date", "mother_id", "mother_offspring_wins"]
        ].sort_values("race_date")

        # Steg 3: cumcount per far
        father_wins = (
            wins_df[wins_df["father_id"].notna()]
            .sort_values(["father_id", "race_date"])
            .reset_index(drop=True)
        )
        father_wins["father_offspring_wins"] = (
            father_wins.groupby("father_id").cumcount() + 1
        )
        father_lookup = father_wins[
            ["race_date", "father_id", "father_offspring_wins"]
        ].sort_values("race_date")

        # Steg 4: merge_asof - strikt < race_date
        df_sorted = df.sort_values("race_date").copy()
        df_sorted["_orig_index"] = df_sorted.index

        df_sorted = pd.merge_asof(
            df_sorted,
            mother_lookup,
            on="race_date",
            by="mother_id",
            direction="backward",
            allow_exact_matches=False,
        )

        df_sorted = pd.merge_asof(
            df_sorted,
            father_lookup,
            on="race_date",
            by="father_id",
            direction="backward",
            allow_exact_matches=False,
        )

        df_sorted["mother_offspring_wins"] = (
            df_sorted["mother_offspring_wins"].fillna(0).astype("int64")
        )
        df_sorted["father_offspring_wins"] = (
            df_sorted["father_offspring_wins"].fillna(0).astype("int64")
        )

        # Återställ ursprunglig ordning
        df_sorted = df_sorted.set_index("_orig_index").sort_index()
        df_sorted.index = original_index
        df_sorted.index.name = df.index.name

        return df_sorted
'''


def patch() -> None:
    content = BUILDER_PATH.read_text()

    # Match från "def _add_pedigree_features" upp till och med "return df"
    # på det sista returstatement i funktionen (de två df merges följt av två
    # fillna och slutligen "return df").
    pattern = re.compile(
        r"    def _add_pedigree_features\(self, df: pd\.DataFrame\) -> pd\.DataFrame:.*?"
        r'        df\["mother_offspring_wins"\] = df\["mother_offspring_wins"\]\.fillna\(0\)\.astype\("int64"\)\n'
        r"        return df\n",
        re.DOTALL,
    )

    matches = pattern.findall(content)
    if not matches:
        print("FEL: hittade inte funktionen att ersätta")
        print("Letar efter pattern som börjar med 'def _add_pedigree_features'")
        print("och slutar med 'mother_offspring_wins...fillna(0)...return df'")
        return

    if len(matches) > 1:
        print(f"FEL: hittade {len(matches)} matchningar, väntade 1")
        return

    new_content = pattern.sub(NEW_FUNCTION, content)
    BUILDER_PATH.write_text(new_content)
    print(f"OK: {BUILDER_PATH} uppdaterad med time-aware pedigree-features")


if __name__ == "__main__":
    patch()
