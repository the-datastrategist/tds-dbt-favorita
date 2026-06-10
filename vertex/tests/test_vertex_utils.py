"""Tests for deprecated vertex_utils shims."""

import pytest

from vertex.utils.vertex_utils import VertexModelSaver


@pytest.mark.unit
class TestDeprecatedVertexUtils:
    def test_vertex_model_saver_emits_deprecation(self):
        with pytest.warns(DeprecationWarning):
            saver = VertexModelSaver({"name": "test"}, object())
        assert saver.model_name.startswith("test")
