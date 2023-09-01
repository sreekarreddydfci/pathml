from pathml.preprocessing.tilestitcher import TileStitcher
import pytest
import os
from unittest.mock import MagicMock, patch
import glob
import jpype


@pytest.fixture(scope="module")
def tile_stitcher():
    os.environ["JAVA_HOME"] = "/usr/lib/jvm/jdk-17/"
    qupath_jars = glob.glob(os.path.abspath("/home/jupyter/Projects/tile_stitching/tools/QuPath/lib/app/*.jar"))
    qupath_jars.append(
        os.path.abspath("/home/jupyter/Projects/tile_stitching/tools/QuPath/lib/app/libopenslide-jni.so")
    )
    stitcher = TileStitcher(qupath_jars)
    stitcher._start_jvm()  # Ensure the JVM starts and QuPath classes are imported
    return stitcher



def test_set_environment_paths(tile_stitcher):
    tile_stitcher.set_environment_paths()
    assert "JAVA_HOME" in os.environ


def test_get_system_java_home(tile_stitcher):
    path = tile_stitcher.get_system_java_home()
    assert isinstance(path, str)


@patch("pathml.preprocessing.tilestitcher.jpype.startJVM")
def test_start_jvm(mocked_jvm, tile_stitcher):
    # Check if JVM was already started
    if jpype.isJVMStarted():
        pytest.skip("JVM was already started, so we skip this test.")
    tile_stitcher._start_jvm()
    mocked_jvm.assert_called()

@patch("pathml.preprocessing.tilestitcher.tifffile")
def test_parse_region(mocked_tifffile, tile_stitcher):
    # Mock the return values
    mocked_tifffile.return_value.__enter__.return_value.pages[
        0
    ].tags.get.side_effect = [
        MagicMock(value=(0, 1)),  # XPosition
        MagicMock(value=(0, 1)),  # YPosition
        MagicMock(value=(1, 1)),  # XResolution
        MagicMock(value=(1, 1)),  # YResolution
        MagicMock(value=100),  # ImageLength
        MagicMock(value=100),  # ImageWidth
    ]
    filename = "tests/testdata/MISI3542i_M3056_3_Panel1_Scan1_[10530,40933]_component_data.tif"
    region = tile_stitcher.parseRegion(filename)
    assert region is not None
    assert isinstance(region, tile_stitcher.ImageRegion)


def test_collect_tif_files(tile_stitcher):
    # Assuming a directory with one tif file for testing
    dir_path = "some_directory"
    os.makedirs(dir_path, exist_ok=True)
    with open(os.path.join(dir_path, "test.tif"), "w") as f:
        f.write("test content")

    files = tile_stitcher._collect_tif_files(dir_path)
    assert len(files) == 1
    assert "test.tif" in files[0]

    os.remove(os.path.join(dir_path, "test.tif"))
    os.rmdir(dir_path)


def test_checkTIFF_valid(tile_stitcher, tmp_path):
    # Create a mock TIFF file
    tiff_path = tmp_path / "mock.tiff"
    tiff_path.write_bytes(b"II*\x00")  # Little-endian TIFF signature
    assert tile_stitcher.checkTIFF(tiff_path) == True


def test_checkTIFF_invalid(tile_stitcher, tmp_path):
    # Create a mock non-TIFF file
    txt_path = tmp_path / "mock.txt"
    txt_path.write_text("Not a TIFF file")
    assert tile_stitcher.checkTIFF(txt_path) == False


def test_checkTIFF_nonexistent(tile_stitcher):
    # Test with a file that doesn't exist
    with pytest.raises(FileNotFoundError):
        tile_stitcher.checkTIFF("nonexistent_file.tiff")


def test_check_tiff(tile_stitcher):
    valid_tif = b"II*"
    invalid_tif = b"abcd"

    with open("valid_test.tif", "wb") as f:
        f.write(valid_tif)

    with open("invalid_test.tif", "wb") as f:
        f.write(invalid_tif)

    assert tile_stitcher.checkTIFF("tests/testdata/smalltif.tif") is True
    assert tile_stitcher.checkTIFF("invalid_test.tif") is False

    os.remove("valid_test.tif")
    os.remove("invalid_test.tif")


def test_get_outfile_ending_with_ome_tif(tile_stitcher):
    result = tile_stitcher._get_outfile("test.ome.tif")
    assert str(result) == "test.ome.tif"


def test_get_outfile_without_ending(tile_stitcher):
    result = tile_stitcher._get_outfile("test")
    assert str(result) == "test.ome.tif"
