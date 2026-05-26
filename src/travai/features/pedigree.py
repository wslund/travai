"""Time-aware pedigree-features.

Ersätter den läckande versionen av _add_pedigree_features i builder.py.

Originalets bug: räknade total summa av alla syskons vinster över hela
dataset, vilket gav future leakage (2018-start såg 2024-vinster).

Den här versionen använder pandas merge_asof för att, för varje (häst,
race_date), hitta antalet vinster av föräldrar's avkomma som inträffade
STRIKT FÖRE den startens datum.

Strategi:
1. Filtrera ut vinster ur data (finish_position == 1)
2. Per förälder, sortera vinster efter datum och cumcount
3. För varje start: använd merge_asof för att hitta cumcount strikt < race_date
"""

import pandas as pd


def add_pedigree_features_time_aware(df: pd.DataFrame) -> pd.DataFrame:
    """Tidsmedvetna pedigree-features.

    För varje start: antalet vinster av syskon (samma mother_id/father_id)
    som inträffade STRIKT FÖRE start.race_date.

    Args:
        df: DataFrame med kolumner: race_date, horse_id, mother_id, father_id,
            finish_position. Måste innehålla alla starter i hela datasetet
            (inte bara t.ex. en delmängd) för att räkningen ska bli rätt.

    Returns:
        DataFrame med samma rader plus två nya kolumner:
        - mother_offspring_wins (int64): vinster av modern's avkomma före
        - father_offspring_wins (int64): vinster av faderns avkomma före

    Algorithm:
        Pandas merge_asof med direction='backward' och
        allow_exact_matches=False ger oss "senaste värdet strikt före".
        Det betyder en vinst som inträffade på samma datum inte räknas in,
        vilket är önskat (vi vill inte att en vinst av syskon i samma
        lopp eller samma dag ska "leak" till features).
    """
    # Bevara originalindex för att kunna återställa ordning
    original_index = df.index.copy()
    df = df.copy()

    # ------- Steg 1: hitta alla vinster med föräldrar -------
    wins_df = df.loc[
        df["finish_position"] == 1,
        ["race_date", "horse_id", "mother_id", "father_id"],
    ].copy()

    # ------- Steg 2: cumcount per mor -------
    mother_wins = (
        wins_df[wins_df["mother_id"].notna()]
        .sort_values(["mother_id", "race_date"])
        .reset_index(drop=True)
    )
    mother_wins["mother_offspring_wins"] = mother_wins.groupby("mother_id").cumcount() + 1
    mother_lookup = mother_wins[["race_date", "mother_id", "mother_offspring_wins"]].sort_values(
        "race_date"
    )

    # ------- Steg 3: cumcount per far -------
    father_wins = (
        wins_df[wins_df["father_id"].notna()]
        .sort_values(["father_id", "race_date"])
        .reset_index(drop=True)
    )
    father_wins["father_offspring_wins"] = father_wins.groupby("father_id").cumcount() + 1
    father_lookup = father_wins[["race_date", "father_id", "father_offspring_wins"]].sort_values(
        "race_date"
    )

    # ------- Steg 4: merge_asof med direction='backward', strikt < race_date -------
    # merge_asof kräver att höger DF är sorterad per "on" - klart ovan
    # Vänster DF måste också vara sorterad per "on"
    df_sorted = df.sort_values("race_date").copy()
    df_sorted["_orig_index"] = df_sorted.index

    df_sorted = pd.merge_asof(
        df_sorted,
        mother_lookup,
        on="race_date",
        by="mother_id",
        direction="backward",
        allow_exact_matches=False,  # strikt < race_date
    )

    df_sorted = pd.merge_asof(
        df_sorted,
        father_lookup,
        on="race_date",
        by="father_id",
        direction="backward",
        allow_exact_matches=False,
    )

    # Fyll NA med 0 och casta till int64
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
