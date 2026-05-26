"""Tester för time-aware pedigree-features."""

from uuid import uuid4

import pandas as pd

from travai.features.pedigree import add_pedigree_features_time_aware


def test_no_prior_wins_returns_zero() -> None:
    """En första start utan tidigare syskonsegrar ger 0."""
    mother = uuid4()
    father = uuid4()
    horse = uuid4()

    df = pd.DataFrame(
        {
            "race_date": [pd.Timestamp("2020-01-01")],
            "horse_id": [horse],
            "mother_id": [mother],
            "father_id": [father],
            "finish_position": [1],
        }
    )

    result = add_pedigree_features_time_aware(df)
    assert result["mother_offspring_wins"].iloc[0] == 0
    assert result["father_offspring_wins"].iloc[0] == 0


def test_sibling_wins_counted_before_only() -> None:
    """En vinst av syskon räknas bara i feature för SENARE starter."""
    mother = uuid4()
    father = uuid4()
    horse_a = uuid4()  # vinner 2020-01-01
    horse_b = uuid4()  # tävlar 2020-06-01

    df = pd.DataFrame(
        {
            "race_date": [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-06-01"),
            ],
            "horse_id": [horse_a, horse_b],
            "mother_id": [mother, mother],
            "father_id": [father, father],
            "finish_position": [1, 5],  # A vinner, B blir 5:a
        }
    )

    result = add_pedigree_features_time_aware(df)
    # Horse A (första) har 0 tidigare syskonsegrar
    a_row = result[result["horse_id"] == horse_a].iloc[0]
    assert a_row["mother_offspring_wins"] == 0
    assert a_row["father_offspring_wins"] == 0
    # Horse B (senare) ser A:s vinst
    b_row = result[result["horse_id"] == horse_b].iloc[0]
    assert b_row["mother_offspring_wins"] == 1
    assert b_row["father_offspring_wins"] == 1


def test_same_day_wins_not_leaked() -> None:
    """Vinster av syskon på SAMMA datum räknas inte (allow_exact_matches=False)."""
    mother = uuid4()
    father = uuid4()
    horse_a = uuid4()
    horse_b = uuid4()

    df = pd.DataFrame(
        {
            "race_date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-01")],
            "horse_id": [horse_a, horse_b],
            "mother_id": [mother, mother],
            "father_id": [father, father],
            "finish_position": [1, 1],  # båda vinner samma dag
        }
    )

    result = add_pedigree_features_time_aware(df)
    # Ingen ska se den andras vinst eftersom det är samma datum
    assert (result["mother_offspring_wins"] == 0).all()
    assert (result["father_offspring_wins"] == 0).all()


def test_unrelated_parents_not_counted() -> None:
    """Vinster av hästar med ANDRA föräldrar räknas inte."""
    mother_a = uuid4()
    mother_b = uuid4()
    father_a = uuid4()
    father_b = uuid4()

    df = pd.DataFrame(
        {
            "race_date": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-06-01")],
            "horse_id": [uuid4(), uuid4()],
            "mother_id": [mother_a, mother_b],  # OLIKA mödrar
            "father_id": [father_a, father_b],
            "finish_position": [1, 5],
        }
    )

    result = add_pedigree_features_time_aware(df)
    # Den senare starten har annan mor och far -> 0 syskonsegrar
    later = result[result["race_date"] == pd.Timestamp("2020-06-01")].iloc[0]
    assert later["mother_offspring_wins"] == 0
    assert later["father_offspring_wins"] == 0


def test_missing_parents_returns_zero() -> None:
    """Om mor/far saknas (None) ska vi få 0 för den raden."""
    horse_a = uuid4()
    df = pd.DataFrame(
        {
            "race_date": [pd.Timestamp("2020-01-01")],
            "horse_id": [horse_a],
            "mother_id": [None],
            "father_id": [None],
            "finish_position": [1],
        }
    )

    result = add_pedigree_features_time_aware(df)
    assert result["mother_offspring_wins"].iloc[0] == 0
    assert result["father_offspring_wins"].iloc[0] == 0


def test_cumulative_count_across_time() -> None:
    """En mor med 3 avkommor som vinner i tur och ordning -> 0, 1, 2."""
    mother = uuid4()
    father = uuid4()

    df = pd.DataFrame(
        {
            "race_date": [
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-03-01"),
                pd.Timestamp("2020-06-01"),
                pd.Timestamp("2020-09-01"),
            ],
            "horse_id": [uuid4(), uuid4(), uuid4(), uuid4()],
            "mother_id": [mother, mother, mother, mother],
            "father_id": [father, father, father, father],
            "finish_position": [1, 1, 1, 5],  # 3 vinster, sista är 5:a
        }
    )

    result = add_pedigree_features_time_aware(df).sort_values("race_date")
    # Efter ordning: 0, 1, 2, 3 syskonsegrar före varje start
    assert list(result["mother_offspring_wins"]) == [0, 1, 2, 3]
    assert list(result["father_offspring_wins"]) == [0, 1, 2, 3]
