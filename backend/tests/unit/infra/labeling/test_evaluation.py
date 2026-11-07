from infra.labeling.evaluation import LabeledBox, score_boxes
from infra.labeling.instances import OrientedBox


def labelled(asset_class, x):
    return LabeledBox(asset_class, OrientedBox((x, 0.5, 0.0), (1.0, 1.0, 1.0), 0.0))


def test_recall_and_label_accuracy():
    truth = [labelled("PROCESS_PUMP", 0), labelled("ELECTRIC_MOTOR", 5), labelled("CONTROL_VALVE", 10)]
    predicted = [labelled("PROCESS_PUMP", 0.1), labelled("PROCESS_PUMP", 5.1), labelled("CONTROL_VALVE", 40)]
    score = score_boxes(truth, predicted)
    assert score["found"] == 2
    assert abs(score["recall"] - 2 / 3) < 1e-9
    assert score["label_accuracy"] == 0.5


def test_empty_truth_and_empty_prediction_do_not_divide_by_zero():
    assert score_boxes([], [])["recall"] == 0.0
    assert score_boxes([labelled("X", 0)], [])["label_accuracy"] == 0.0


def test_one_prediction_cannot_satisfy_two_truth_boxes():
    truth = [labelled("A", 0), labelled("A", 0.2)]
    assert score_boxes(truth, [labelled("A", 0.1)])["found"] == 1
