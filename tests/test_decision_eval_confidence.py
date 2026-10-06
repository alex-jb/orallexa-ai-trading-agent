"""Offline checks for confidence-score buckets, using resolved input rows."""
from eval.decision_eval import confidence_calibration
from models.confidence import scale_confidence


def test_capped_confidence_is_in_final_bucket():
    result = confidence_calibration([{
        "confidence": scale_confidence(100),
        "correct": True,
        "forward_return": 0.02,
    }])
    assert result["total_evaluated"] == 1
    assert sum(bucket["count"] for bucket in result["buckets"]) == 1
    assert result["buckets"][-1] == {
        "range": "65-82", "count": 1, "accuracy": 1.0, "avg_return": 0.02,
    }


def test_bucket_boundaries_count_each_valid_score_once():
    scores = [0, 29.9, 30, 49.9, 50, 64.9, 65, 81.9, 82]
    rows = [{"confidence": score, "correct": score == 82,
             "forward_return": 0.03 if score == 82 else 0.0}
            for score in scores]
    result = confidence_calibration(rows)
    assert [bucket["range"] for bucket in result["buckets"]] == [
        "0-30", "30-50", "50-65", "65-82",
    ]
    assert [bucket["count"] for bucket in result["buckets"]] == [2, 2, 2, 3]
    assert sum(bucket["count"] for bucket in result["buckets"]) == len(scores)
    assert result["buckets"][-1]["accuracy"] == 0.333
    assert result["buckets"][-1]["avg_return"] == 0.01


def test_scores_outside_supported_range_do_not_enter_buckets():
    result = confidence_calibration([{"confidence": score} for score in [-1, 82.1]])
    assert result["total_evaluated"] == 2
    assert all(bucket["count"] == 0 for bucket in result["buckets"])


def test_empty_confidence_report_keeps_bucket_shape():
    result = confidence_calibration([])
    assert result["total_evaluated"] == 0
    assert all(bucket["count"] == 0 and bucket["accuracy"] is None
               for bucket in result["buckets"])
