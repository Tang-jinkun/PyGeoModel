from pathlib import Path

from app.core.config import settings
from app.services.output_files import describe_output_file, describe_output_files, list_task_output_files, resolve_task_output_path


def test_describe_output_file_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "visible.geojson"
    path.write_text("{}", encoding="utf-8")

    info = describe_output_file("task_a", "visible_geojson", path)

    assert info.kind == "visible_geojson"
    assert info.label == "Visible Area GeoJSON"
    assert info.url == "/outputs/task_a/visible.geojson"
    assert info.download_url == "/api/radar/coverage/task_a/outputs/visible_geojson"
    assert info.filename == "visible.geojson"
    assert info.media_type == "application/geo+json"
    assert info.size_bytes == 2
    assert info.exists is True


def test_describe_output_file_missing_file(tmp_path: Path) -> None:
    info = describe_output_file("task_a", "viewshed_tif", tmp_path / "viewshed.tif")

    assert info.exists is False
    assert info.size_bytes is None
    assert info.media_type == "image/tiff"


def test_describe_output_files_preserves_order(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    first.write_text("a", encoding="utf-8")
    second.write_text("b", encoding="utf-8")

    infos = describe_output_files(
        "task_a",
        {
            "model_metadata_json": first,
            "output_manifest_json": second,
        },
    )

    assert [item.kind for item in infos] == ["model_metadata_json", "output_manifest_json"]


def test_resolve_task_output_path_uses_whitelist_filename(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()

    path = resolve_task_output_path("task_a", "blocked_geojson")

    assert path == (tmp_path / "outputs" / "task_a" / "blocked.geojson").resolve()


def test_list_task_output_files_refreshes_real_file_state(tmp_path: Path) -> None:
    settings.data_dir = tmp_path
    settings.ensure_directories()
    output_dir = tmp_path / "outputs" / "task_a"
    output_dir.mkdir(parents=True)
    (output_dir / "viewshed.tif").write_bytes(b"abc")

    files = list_task_output_files("task_a")
    viewshed = next(item for item in files if item.kind == "viewshed_tif")
    visible = next(item for item in files if item.kind == "visible_geojson")

    assert viewshed.exists is True
    assert viewshed.size_bytes == 3
    assert visible.exists is False
