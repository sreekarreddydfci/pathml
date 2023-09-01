import os
import glob
import jpype
import tifffile
import traceback


class TileStitcher:
    """
    This class provides utilities to stitch TIFF tiles using QuPath.

    Make sure QuPath and JDK are installed before using this class.
    """

    def __init__(self, qupath_jarpath=[], java_path=None, memory="40g"):
        """
        Initialize the TileStitcher by setting up the Java Virtual Machine and QuPath environment.
        """

        if java_path:
            os.environ["JAVA_HOME"] = java_path
        else:
            self.set_environment_paths()

        self.classpath = os.pathsep.join(qupath_jarpath)
        self.memory = memory
        self._start_jvm()

    def __del__(self):
        """Ensure the JVM is shutdown when the object is deleted."""
        jpype.shutdownJVM()

    @staticmethod
    def set_environment_paths():
        """
        Set the JAVA_HOME path based on the OS type.
        If the path is not found in the predefined paths dictionary, the function tries
        to automatically find the JAVA_HOME path from the system.
        """
        os_type = os.name
        paths = {
            "posix": "/usr/lib/jvm/jdk-17/",
            # Extend this dictionary for other OS types if needed
        }
        java_path = paths.get(os_type, TileStitcher.get_system_java_home())
        print(f"Java path not specified , Setting Java path to {java_path}")
        os.environ["JAVA_HOME"] = java_path

    @staticmethod
    def get_system_java_home():
        """
        Try to automatically find the JAVA_HOME path from the system.
        Return it if found, otherwise return an empty string.
        """
        try:
            java_home = os.popen("echo $JAVA_HOME").read().strip()
            return java_home
        except Exception as e:
            print(f"Error retrieving JAVA_HOME from the system: {e}")
            return ""

    def run_image_stitching(self, infiles, fileout):
        """
        Perform image stitching on the provided TIFF files and output a stitched OME-TIFF image.
        """
        try:
            infiles = self._collect_tif_files(infiles)
            fileout = self._get_outfile(fileout)

            if not infiles or not fileout:
                return

            server = self.parse_regions(infiles)
            server = self.ImageServers.pyramidalize(server)
            self._write_pyramidal_image_server(server, fileout)

            server.close()
            print(f"Image stitching completed. Output file: {fileout}")

        except Exception as e:
            print(f"Error running image stitching: {e}")
            traceback.print_exc()

    def _start_jvm(self):
        """Start the Java Virtual Machine and import necessary QuPath classes."""
        if not jpype.isJVMStarted():
            try:
                # Change it to -Xmx10g or any other value, based on the available system memory.
                jpype.startJVM(
                    f"-Xmx{self.memory}", "-Djava.class.path=%s" % self.classpath
                )
                self._import_qupath_classes()
            except Exception as e:
                print(f"Error occurred while starting JVM: {e}")
                traceback.print_exc()
                exit(1)

    def _import_qupath_classes(self):
        """Import necessary QuPath classes after starting JVM."""

        try:
            print("Importing required qupath classes")
            self.ImageServerProvider = jpype.JPackage(
                "qupath.lib.images.servers"
            ).ImageServerProvider
            self.ImageServers = jpype.JPackage("qupath.lib.images.servers").ImageServers
            self.SparseImageServer = jpype.JPackage(
                "qupath.lib.images.servers"
            ).SparseImageServer
            self.OMEPyramidWriter = jpype.JPackage(
                "qupath.lib.images.writers.ome"
            ).OMEPyramidWriter
            self.ImageRegion = jpype.JPackage("qupath.lib.regions").ImageRegion
            self.ImageIO = jpype.JPackage("javax.imageio").ImageIO
            self.BaselineTIFFTagSet = jpype.JPackage(
                "javax.imageio.plugins.tiff"
            ).BaselineTIFFTagSet
            self.TIFFDirectory = jpype.JPackage(
                "javax.imageio.plugins.tiff"
            ).TIFFDirectory
            self.BufferedImage = jpype.JPackage("java.awt.image").BufferedImage

        except Exception as e:
            raise RuntimeError(f"Failed to import QuPath classes: {e}")

    def _collect_tif_files(self, input):
        """Collect .tif files from the input directory or list."""
        if isinstance(input, str) and os.path.isdir(input):
            return glob.glob(os.path.join(input, "**/*.tif"), recursive=True)
        elif isinstance(input, list):
            return [file for file in input if file.endswith(".tif")]
        else:
            print(
                f"Input must be a directory path or list of .tif files. Received: {input}"
            )
            return []

    def _get_outfile(self, fileout):
        """Get the output file object for the stitched image."""
        if not fileout.endswith(".ome.tif"):
            fileout += ".ome.tif"
        return jpype.JClass("java.io.File")(fileout)

    def parseRegion(self, file, z=0, t=0):
        if self.checkTIFF(file):
            try:
                # Extract the image region coordinates and dimensions from the TIFF tags
                with tifffile.TiffFile(file) as tif:
                    tag_xpos = tif.pages[0].tags.get("XPosition")
                    tag_ypos = tif.pages[0].tags.get("YPosition")
                    tag_xres = tif.pages[0].tags.get("XResolution")
                    tag_yres = tif.pages[0].tags.get("YResolution")
                    if (
                        tag_xpos is None
                        or tag_ypos is None
                        or tag_xres is None
                        or tag_yres is None
                    ):
                        print(f"Could not find required tags for {file}")
                        return None
                    xpos = 10000 * tag_xpos.value[0] / tag_xpos.value[1]
                    xres = tag_xres.value[0] / (tag_xres.value[1] * 10000)
                    ypos = 10000 * tag_ypos.value[0] / tag_ypos.value[1]
                    yres = tag_yres.value[0] / (tag_yres.value[1] * 10000)
                    height = tif.pages[0].tags.get("ImageLength").value
                    width = tif.pages[0].tags.get("ImageWidth").value
                x = int(round(xpos * xres))
                y = int(round(ypos * yres))
                # Create an ImageRegion object representing the extracted image region
                region = self.ImageRegion.createInstance(x, y, width, height, z, t)
                return region
            except Exception as e:
                print(f"Error occurred while parsing {file}: {e}")
                traceback.print_exc()
        else:
            print(f"{file} is not a valid TIFF file")

    # Define a function to check if a file is a valid TIFF file
    def checkTIFF(self, file):
        try:
            with open(file, "rb") as f:
                bytes = f.read(4)
                byteOrder = self.toShort(bytes[0], bytes[1])
                if byteOrder == 0x4949:  # Little-endian
                    val = self.toShort(bytes[3], bytes[2])
                elif byteOrder == 0x4D4D:  # Big-endian
                    val = self.toShort(bytes[2], bytes[3])
                else:
                    return False
                return val == 42 or val == 43
        except FileNotFoundError:
            print(f"Error: File not found {file}")
            raise FileNotFoundError
        except IOError:
            print(f"Error: Could not open file {file}")
            raise IOError
        except Exception as e:
            print(f"Error: {e}")

    # Define a helper function to convert two bytes to a short integer
    def toShort(self, b1, b2):
        return (b1 << 8) + b2

    # Define a function to parse TIFF file metadata and extract the image region
    def parse_regions(self, infiles):
        builder = self.SparseImageServer.Builder()
        for f in infiles:
            try:
                region = self.parseRegion(f)
                if region is None:
                    print("WARN: Could not parse region for " + str(f))
                    continue
                serverBuilder = (
                    self.ImageServerProvider.getPreferredUriImageSupport(
                        self.BufferedImage, jpype.JString(f)
                    )
                    .getBuilders()
                    .get(0)
                )
                builder.jsonRegion(region, 1.0, serverBuilder)
            except Exception as e:
                print(f"Error parsing regions from file {f}: {e}")
                traceback.print_exc()
        return builder.build()

    def _write_pyramidal_image_server(self, server, fileout, downsamples=[1, 32]):
        """Convert the parsed image regions into a pyramidal image server and write to file."""
        # Convert the parsed regions into a pyramidal image server and write to file

        try:
            newOME = self.OMEPyramidWriter.Builder(server)

            # Control downsamples
            if downsamples is None:
                downsamples = server.getPreferredDownsamples()
                print(downsamples)
            newOME.downsamples(downsamples).tileSize(
                512
            ).channelsInterleaved().parallelize().losslessCompression().build().writePyramid(
                fileout.getAbsolutePath()
            )
        except Exception as e:
            print(f"Error writing pyramidal image server to file {fileout}: {e}")
            traceback.print_exc()
