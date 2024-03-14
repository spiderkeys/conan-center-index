from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.env import VirtualBuildEnv, VirtualRunEnv
from conan.tools.files import chdir, copy, get, rmdir
from conan.tools.gnu import Autotools, AutotoolsToolchain, AutotoolsDeps
from conan.tools.scm import Version
from conan.tools.build import cross_building
import os

required_conan_version = ">=1.53.0"


class LibsndioConan(ConanFile):
    name = "libsndio"
    license = "ISC"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://sndio.org/"
    topics = ("sndio", "sound", "audio", "midi")
    description = "A small audio and MIDI framework that provides a lightweight audio & MIDI server \
        and a user-space API to access either the server or the hardware directly in a uniform way."
    package_type = "shared-library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "with_alsa": [True, False]
    }
    default_options = {
        "with_alsa": True
    }

    def configure(self):
        if self.options.get_safe("with_alsa"):
            self.requires("libalsa/1.2.10")
            self.options["libalsa/*"].shared = True

        self.settings.rm_safe("compiler.libcxx")
        self.settings.rm_safe("compiler.cppstd")

    def validate(self):
        if self.settings.os != "Linux":
            raise ConanInvalidConfiguration(f"{self.ref} only supports Linux")

    def build_requirements(self):
        self.tool_requires("libtool/2.4.7")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        virtual_build_env = VirtualBuildEnv(self)
        virtual_build_env.generate()

        # # inject requires env vars in build scope
        # # it's required in case of native build when there is AutotoolsDeps & at least one dependency which might be shared, because configure tries to run a test executable
        if not cross_building(self):
            env = VirtualRunEnv(self)
            env.generate(scope="build")

        tc = AutotoolsToolchain(self)

        # Set expected config
        tc.configure_args.append( "--datadir=${prefix}/res" )

        # Bundled `configure` script does not support these options, so remove
        exclusions = ["--enable-shared", "--disable-shared", "--disable-static", "--enable-static", "--sbindir", "--oldincludedir"]
        tc.configure_args = [arg for arg in tc.configure_args if not any(exclusion in arg for exclusion in exclusions)]

        # Add alsa support
        if self.options.get_safe("with_alsa"):
            tc.configure_args.append("--enable-alsa")
        else:
            tc.configure_args.append("--disable-alsa")

        # Inject conan dependency information into sndio configuration
        dep_cflags = []
        dep_ldflags = []
        for dependency in reversed(self.dependencies.host.topological_sort.values()):
            deps_cpp_info = dependency.cpp_info.aggregated_components()

            dep_cflags.extend( deps_cpp_info.cflags + deps_cpp_info.defines )
            for path in deps_cpp_info.includedirs:
                dep_cflags.append( f"-I{path}" )

            dep_ldflags.extend( deps_cpp_info.sharedlinkflags + deps_cpp_info.exelinkflags )
            for path in deps_cpp_info.libdirs:
                dep_ldflags.append( f"-L{path}" )
            for lib in reversed(deps_cpp_info.libs + deps_cpp_info.system_libs):
                dep_ldflags.append( f"-l{lib}" )

        cflags = ' '.join([flag for flag in dep_cflags])
        ldflags = ' '.join([flag for flag in dep_ldflags])
        tc.configure_args.extend([
            f"CFLAGS={cflags}",
            f"LDFLAGS={ldflags}"
        ])

        tc.generate()

        tc = AutotoolsDeps(self)
        tc.generate()

    def build(self):
        autotools = Autotools(self)
        if Version(self.version) > "1.2.4":
            autotools.configure()
            autotools.make()
        else:
            with chdir(self, self.source_folder):
                autotools.configure()
                autotools.make()

    def package(self):
        copy(self, "LICENSE", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        if Version(self.version) > "1.2.4":
            autotools = Autotools(self)
            autotools.install()
        else:
            with chdir(self, self.source_folder):
                autotools = Autotools(self)
                autotools.install()
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        rmdir(self, os.path.join(self.package_folder, "share"))
        rmdir(self, os.path.join(self.package_folder, "bin"))

    def package_info(self):
        self.cpp_info.set_property("cmake_find_mode", "both")
        self.cpp_info.set_property("cmake_file_name", "sndio")
        self.cpp_info.set_property("cmake_target_name", "sndio::sndio")
        self.cpp_info.set_property("pkg_config_name", "sndio")
        self.cpp_info.libs = ["sndio"]
        self.cpp_info.system_libs = ["dl", "m", "rt"]

        # TODO: to remove in conan v2?
        self.cpp_info.names["cmake_find_package"] = "sndio"
        self.cpp_info.names["cmake_find_package_multi"] = "sndio"
        self.cpp_info.names["pkg_config"] = "sndio"
