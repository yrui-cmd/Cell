"""Offline checks for the required user-question gate."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("ppt_handoff_gate", Path(__file__).resolve().parents[1] / "scripts/handoff.py")
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class QuestionGateTests(unittest.TestCase):
    def setUp(self):
        self.task = {
            "questions_locked": True,
            "design": {"style": "清晰学术", "language": "中文", "aspect_ratio": "16:9", "palette": "蓝白", "page_count": 1},
            "template_notes": "无模板",
            "questions": [{"field": key, "question": "请确认这一项？", "asked": True,
                           "answer": "按推荐", "state": "confirmed", "response_source": "用户回复：按推荐"}
                          for key in sorted(handoff.REQUIRED_QUESTIONS)],
            "timing": {"total": 60, "talk": 60, "qa": 0, "includes_qa": False},
            "sources": [], "original_request": "离线测试资料",
            "pages": [{"kind": "content", "title": "测试", "story": "内容", "evidence": "资料",
                       "visual": "图示", "content": "真实上屏内容", "layout": "左图右文", "notes": "注释不直接上屏", "seconds": 60}],
        }

    def test_complete_answers_build_verified_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "handoff"
            result = handoff.build(self.task, root)
            self.assertEqual(result["credits"], 1)
            self.assertEqual(handoff.inspect(root), result)

    def test_incomplete_or_inferred_answers_do_not_create_output(self):
        variants = []
        task = copy.deepcopy(self.task)
        task["questions"].pop()
        variants.append(task)
        task = copy.deepcopy(self.task)
        task["questions"].append(copy.deepcopy(task["questions"][0]))
        variants.append(task)
        for key, value in [("asked", False), ("asked", "true"), ("response_source", ""),
                           ("question", ""), ("answer", ""), ("state", "inferred")]:
            task = copy.deepcopy(self.task)
            task["questions"][0][key] = value
            variants.append(task)
        for task in variants:
            with self.subTest(task=task), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "handoff"
                with self.assertRaises(ValueError):
                    handoff.build(task, root)
                self.assertFalse(root.exists())

    def test_delegation_still_requires_question_and_user_reply(self):
        self.task["questions"][0]["state"] = "delegated"
        handoff.validate_spec(self.task)
        del self.task["questions"][0]["response_source"]
        with self.assertRaises(ValueError):
            handoff.validate_spec(self.task)


if __name__ == "__main__":
    unittest.main()
