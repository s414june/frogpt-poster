import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpt_package.policy import PosterPolicy
from gpt_package.types import ImageSource, PosterAssetSet, PosterRequest


class PosterPolicyTests(unittest.TestCase):
    def test_policy_prefers_user_image(self) -> None:
        policy = PosterPolicy()
        request = PosterRequest(
            title="Sale",
            body="Weekend event",
            assets=PosterAssetSet(user_image_paths=["C:\\images\\real-photo.jpg"]),
        )
        decision = policy.decide(request)
        self.assertEqual(decision.image_source, ImageSource.USER_IMAGE)

    def test_policy_falls_back_to_ai_without_user_image(self) -> None:
        policy = PosterPolicy()
        request = PosterRequest(title="Sale", body="Weekend event")
        decision = policy.decide(request)
        self.assertEqual(decision.image_source, ImageSource.AI_FALLBACK)


if __name__ == "__main__":
    unittest.main()
