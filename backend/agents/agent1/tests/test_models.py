from __future__ import annotations

import pytest


torch = pytest.importorskip("torch")

from backend.agents.agent1.src.models import (  # noqa: E402
    AttentionResUNet7ch,
    BuildingUNet,
    DamageUNet,
    RoadUNet,
)


@pytest.mark.parametrize(
    ("model", "channels", "classes"),
    [
        (BuildingUNet(base_channels=4), 3, 1),
        (DamageUNet(base_channels=4), 7, 5),
        (RoadUNet(base_channels=4), 3, 1),
        (AttentionResUNet7ch(base_channels=4), 7, 3),
    ],
)
def test_final_model_output_shapes(model, channels: int, classes: int) -> None:
    model.eval()
    with torch.inference_mode():
        output = model(torch.zeros(1, channels, 64, 64))
    assert tuple(output.shape) == (1, classes, 64, 64)
