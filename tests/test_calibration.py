from bench.calibration import best_yield, free_lunch, sweep


def F(conf, status):
    return {"confidence": conf, "status": status}


def test_sweep_counts_at_each_threshold():
    fields = [F(1.0, "correct"), F(0.9, "correct"), F(0.5, "wrong"), F(0.4, "wrong")]
    rows = {r["threshold"]: r for r in sweep(fields, [0.0, 0.6, 1.0])}

    assert rows[0.0]["coverage"] == 1.0
    assert rows[0.0]["error_rate"] == 0.5
    assert rows[0.0]["yield"] == 0.5

    # gate at 0.6 drops both wrong answers and keeps both correct ones
    assert rows[0.6]["coverage"] == 0.5
    assert rows[0.6]["error_rate"] == 0.0
    assert rows[0.6]["yield"] == 0.5
    assert rows[0.6]["errors_screened"] == 2
    assert rows[0.6]["correct_lost"] == 0

    # gate at 1.0 also costs a correct answer
    assert rows[1.0]["correct_lost"] == 1
    assert rows[1.0]["yield"] == 0.25


def test_free_lunch_is_the_strictest_costless_gate():
    fields = [F(1.0, "correct"), F(0.9, "correct"), F(0.5, "wrong")]
    lunch = free_lunch(sweep(fields, [0.0, 0.6, 0.8, 0.95, 1.0]))
    assert lunch["threshold"] == 0.8       # 0.95 would discard the 0.9 correct
    assert lunch["errors_screened"] == 1
    assert lunch["correct_lost"] == 0


def test_no_free_lunch_when_signal_does_not_separate():
    # wrong answers are the confident ones — no gate helps for free
    fields = [F(0.9, "wrong"), F(0.5, "correct")]
    assert free_lunch(sweep(fields, [0.0, 0.6, 0.95])) is None


def test_best_yield_prefers_the_stricter_gate_on_ties():
    fields = [F(1.0, "correct"), F(0.5, "wrong")]
    best = best_yield(sweep(fields, [0.0, 0.6]))
    assert best["threshold"] == 0.6        # same yield, fewer errors shipped


def test_already_abstained_fields_are_never_counted_as_kept():
    fields = [F(1.0, "abstained"), F(1.0, "correct")]
    row = sweep(fields, [0.0])[0]
    assert row["coverage"] == 0.5
    assert row["yield"] == 0.5


def test_empty_input():
    assert sweep([]) == []
    assert best_yield([]) is None
