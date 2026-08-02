from datetime import UTC, datetime

import pytest

from bamf_lid.models import Dataset, DatasetSource
from bamf_lid.validator import validate_dataset


def test_rejects_empty_dataset():
    dataset = Dataset(
        datasetVersion="test",
        generatedAt=datetime.now(UTC),
        source=DatasetSource(pdfUrl="https://example.test/a.pdf", pdfSha256="0" * 64, onlineTestcenterUrl="https://example.test"),
        questions=[],
    )
    with pytest.raises(ValueError, match="460"):
        validate_dataset(dataset)
