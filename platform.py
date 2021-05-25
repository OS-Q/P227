import copy
import os
import platform

from platformio.managers.platform import PlatformBase
from platformio.util import get_systype


class P227Platform(PlatformBase):

    def configure_default_packages(self, variables, targets):
        if "zephyr" in variables.get("pioframework", []):
            for p in self.packages:
                if p.startswith("framework-zephyr-") or p in (
                        "tool-cmake", "tool-dtc", "tool-ninja"):
                    self.packages[p]["optional"] = False
            if "windows" not in get_systype():
                self.packages["tool-gperf"]["optional"] = False

        upload_protocol = variables.get(
            "upload_protocol",
            self.board_config(variables.get("board")).get(
                "upload.protocol", ""))

        if upload_protocol == "renode" and "debug" not in targets:
            self.packages["tool-renode"]["type"] = "uploader"

        return PlatformBase.configure_default_packages(self, variables, targets)

    def get_boards(self, id_=None):
        result = PlatformBase.get_boards(self, id_)
        if not result:
            return result
        if id_:
            return self._add_default_debug_tools(result)
        else:
            for key, value in result.items():
                result[key] = self._add_default_debug_tools(result[key])
        return result

    def _add_default_debug_tools(self, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload",{}).get("protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        tools = ("jlink", "qemu", "renode", "ftdi", "minimodule",
                "olimex-arm-usb-tiny-h", "olimex-arm-usb-ocd-h",
                "olimex-arm-usb-ocd", "olimex-jtag-tiny", "tumpa")
        for tool in tools:
            if tool in ("qemu", "renode"):
                if not debug.get("%s_machine" % tool):
                    continue
            elif (tool not in upload_protocols or tool in debug["tools"]):
                continue
            if tool == "jlink":
                assert debug.get("jlink_device"), (
                    "Missed J-Link Device ID for %s" % board.id)
                debug["tools"][tool] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun",
                            "-if", "JTAG",
                            "-select", "USB",
                            "-jtagconf", "-1,-1",
                            "-device", debug.get("jlink_device"),
                            "-port", "2331"
                        ],
                        "executable": ("JLinkGDBServerCL.exe"
                                       if platform.system() == "Windows" else
                                       "JLinkGDBServer")
                    },
                    "onboard": tool in debug.get("onboard_tools", [])
                }

            elif tool == "qemu":
                machine64bit = "64" in board.get("build.mabi")
                debug["tools"][tool] = {
                    "server": {
                        "package": "tool-qemu-riscv",
                        "arguments": [
                            "-nographic",
                            "-machine", debug.get("qemu_machine"),
                            "-d", "unimp,guest_errors",
                            "-gdb", "tcp::1234",
                            "-S"
                        ],
                        "executable": "bin/qemu-system-riscv%s" % (
                            "64" if machine64bit else "32")
                    },
                    "onboard": True
                }
            elif tool == "renode":
                assert debug.get("renode_machine"), (
                    "Missing Renode machine ID for %s" % board.id)
                debug["tools"][tool] = {
                    "server": {
                        "package": "tool-renode",
                        "arguments": [
                            "--disable-xwt",
                            "-e", "include @%s" % os.path.join(
                                "scripts", "single-node", debug.get("renode_machine")),
                            "-e", "machine StartGdbServer 3333 True"
                        ],
                        "executable": ("bin/Renode"
                                       if platform.system() == "Windows" else
                                       "renode"),
                        "ready_pattern": "GDB server with all CPUs started on port"

                    },
                    "onboard": True
                }
            else:
                server_args = [
                    "-s", "$PACKAGE_DIR/share/openocd/scripts"
                ]
                sdk_dir = self.get_package_dir("framework-freedom-e-sdk")
                board_cfg = os.path.join(
                    sdk_dir or "", "bsp", "sifive-%s" % board.id, "openocd.cfg")
                if os.path.isfile(board_cfg):
                    server_args.extend(["-f", board_cfg])
                elif board.id == "e310-arty":
                    server_args.extend([
                        "-f", os.path.join("interface", "ftdi", "%s.cfg" % (
                            "arty-onboard-ftdi" if tool == "ftdi" else tool)),
                        "-f", os.path.join(
                            sdk_dir or "", "bsp", "freedom-e310-arty", "openocd.cfg")
                    ])
                else:
                    assert "Unknown debug configuration", board.id
                debug["tools"][tool] = {
                    "server": {
                        "package": "tool-openocd-riscv",
                        "executable": "bin/openocd",
                        "arguments": server_args
                    },
                    "onboard": tool in debug.get("onboard_tools", []),
                    "init_cmds": debug.get("init_cmds", None)
                }

        board.manifest["debug"] = debug
        return board

    def configure_debug_options(self, initial_debug_options, ide_data):
        debug_options = copy.deepcopy(initial_debug_options)
        server_executable = debug_options["server"]["executable"].lower()
        adapter_speed = initial_debug_options.get("speed")
        if adapter_speed:
            if "openocd" in server_executable:
                debug_options["server"]["arguments"].extend(
                    ["-c", "adapter_khz %s" % adapter_speed]
                )
            elif "jlink" in server_executable:
                debug_options["server"]["arguments"].extend(
                    ["-speed", adapter_speed]
                )

        return debug_options
