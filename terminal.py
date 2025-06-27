import re
import sys
import os
import subprocess
import threading
import traceback
from html import escape

import requests
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from src.custom_ascii_magic import CustomAsciiArt
from src.shell_parser import ShellParser
from src.vim_editor import VimEditor


class TerminalEmulator(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.history = []
        self.history_index = -1
        self.current_cmd = ""
        self.current_prompt_block = None
        self.current_dir = os.getcwd()
        self.vim_editor = None
        self.python_process = None
        self.python_input_mode = False
        self.python_input_buffer = ""
        self.last_python_output = ""
        self.is_script_execution = False

        self.environment = {
            'PATH': '/home/user/bin:/usr/bin:/bin',
            'USER': 'user',
            'HOME': '/home/user',
            'PYTERM_VERSION': '0.9'
        }

        self.show_prompt()
        self.init_directory = os.path.join(os.getcwd(), ".pyterm_init")
        self.run_init_scripts()

    def initUI(self):
        self.setWindowTitle('PyTerminal v0.9.')
        self.setGeometry(300, 300, 800, 600)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(False)
        self.terminal.setStyleSheet("""
            QTextEdit {
                background-color: #000000;
                color: #00FF00;
                font-family: 'Consolas', monospace;
                font-size: 12pt;
                border: 2px solid #003300;
                padding: 5px;
                selection-background-color: #00FF00;
                selection-color: #000000;
                scrollbar-width: none;
            }
            QScrollBar {
                display: none;
            }
            QTextEdit::cursor {
                border: 1px solid #00FF00;
                width: 1px;
                height: 1.2em;
                animation: blink 1s step-end infinite;
            }
            @keyframes blink {
                from, to { background-color: transparent; }
                50% { background-color: #00FF00; }
            }
            QTextEdit {
                background-image: linear-gradient(
                    to bottom,
                    rgba(0, 0, 0, 0.1) 50%,
                    rgba(0, 255, 0, 0.05) 50%
                );
                background-size: 100% 4px;
            }
        """)
        self.terminal.setFocusPolicy(Qt.StrongFocus)
        self.terminal.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.terminal.document().setMaximumBlockCount(5000)
        self.terminal.installEventFilter(self)
        self.terminal.setAcceptRichText(False)

        self.setStyleSheet("""
            QWidget {
                background-color: #000000;
                border: 1px solid #003300;
            }
            QMainWindow::title {
                color: #00FF00;
                font-weight: bold;
            }
            QMenu {
                background-color: #000000;
                border: 1px solid #003300;
                margin: 2px;
                font-family: 'Consolas', monospace;
                font-size: 11pt;
                color: #FFFFFF;
            }
            QMenu::item {
                padding: 5px 25px;
            }
            QMenu::item:selected {
                background-color: #003300;
                color: #00FF00;
            }
            QMenu::item:disabled {
                color: #808080;
            }
            QMenu::separator {
                height: 1px;
                background-color: #003300;
                margin: 2px 0;
            }
        """)

        layout = QVBoxLayout()
        layout.addWidget(self.terminal)
        self.setLayout(layout)

    def run_init_scripts(self):
        """自动执行初始化目录中的所有脚本"""
        if not os.path.exists(self.init_directory):
            return

        try:
            script_files = sorted(os.listdir(self.init_directory))
            for script in script_files:
                script_path = os.path.join(self.init_directory, script)
                if os.path.isfile(script_path) and script_path.endswith('.sh'):
                    try:
                        with open(script_path, 'r', encoding="utf-8") as f:
                            script_content = f.read()

                        parser = ShellParser(self)
                        parser.parse(script_content, self.current_dir)

                        self.show_prompt()
                    except Exception as e:
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append(f"start up error: {str(e)}")

        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"初始化目录处理失败: {str(e)}")

    def show_prompt(self):
        """显示经典复古风格的提示符"""
        rel_path = os.path.relpath(self.current_dir, os.getcwd())
        self.current_prompt = f"user@pyterm:{rel_path}$ "
        self.terminal.setTextColor(QColor('#00FF00'))
        if self.terminal.toPlainText() == "":
            self.terminal.append("PyTerminal v0.9")
            self.terminal.append("-" * 50)
            self.terminal.append("Type Help for more information")
            self.terminal.append("")

        self.terminal.append(self.current_prompt)
        self.current_prompt_block = self.terminal.document().lastBlock()
        self.move_cursor_to_end()

    def eventFilter(self, obj, event):
        if obj == self.terminal and event.type() == QEvent.KeyPress:
            if self.vim_editor and self.vim_editor.is_active:
                self.vim_editor.handle_key_press(event)
                self.render_vim_editor()
                if not self.vim_editor.is_active:
                    self.exit_vim_editor()
                    return True
            elif self.python_input_mode:  # 处理Python输入模式
                self.handle_python_input(event)
                return True
            else:
                self.handle_key_press(event)
            return True
        return super().eventFilter(obj, event)

    def move_cursor_to_end(self):
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.terminal.setTextCursor(cursor)

    def execute_command(self):
        self.current_cmd = self.current_cmd.strip()
        if self.current_cmd:
            self.history.append(self.current_cmd)
            self.history_index = len(self.history)

        # 处理Python脚本执行
        if self.current_cmd.startswith(('python', 'python3')):
            self.run_python_script()
            self.current_cmd = ""
            return

        # 处理其他命令...
        if self.current_cmd == "clear":
            self.terminal.clear()
        elif self.current_cmd.startswith("ls"):
            self.ls_command()
        elif self.current_cmd.startswith("cd"):
            self.cd_command()
        elif self.current_cmd == "pwd":
            self.pwd_command()
        elif self.current_cmd.startswith("touch"):
            self.touch_command()
        elif self.current_cmd.startswith("mkdir"):
            self.mkdir_command()
        elif self.current_cmd.startswith("rm"):
            self.rm_command()
        elif self.current_cmd.startswith("cat"):
            self.cat_command()
        elif self.current_cmd.startswith("cp"):
            self.cp_command()
        elif self.current_cmd.startswith("mv"):
            self.mv_command()
        elif self.current_cmd.startswith("echo"):
            self.echo_command()
        elif self.current_cmd.startswith("export"):
            self.export_command()
        elif self.current_cmd.startswith("head"):
            self.head_command()
        elif self.current_cmd.startswith("tail"):
            self.tail_command()
        elif self.current_cmd.startswith("grep"):
            self.grep_command()
        elif self.current_cmd.startswith("sort"):
            self.sort_command()
        elif self.current_cmd.startswith("uniq"):
            self.uniq_command()
        elif self.current_cmd.startswith("asciishow "):
            self.show_ascii_image()
        elif self.current_cmd.startswith("vim"):
            self.vim_command()
        elif self.current_cmd == "help":
            self.show_help()
        elif self.current_cmd == "exit":
            self.close()
        elif self.current_cmd.startswith("curl"):
            self.curl_command()
        elif self.current_cmd.startswith("run"):
            script_path = self.current_cmd[4:].strip()
            self.run_script_file(script_path)
        else:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"pyterm: command not found: {self.current_cmd}")

        self.current_cmd = ""
        if not self.python_input_mode:
            self.show_prompt()

    def run_script_file(self, script_path):
        full_path = os.path.join(self.current_dir, script_path)

        if not os.path.exists(full_path):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"run: {script_path}: No such file or directory")
            return

        if not os.path.isfile(full_path):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"run: {script_path}: Not a file")
            return

        if not script_path.endswith('.sh'):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"run: {script_path}: Not a shell script")
            return

        try:
            with open(full_path, 'r', encoding="utf-8") as f:
                script_content = f.read()

            parser = ShellParser(self)
            parser.parse(script_content, self.current_dir)

        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"执行脚本失败: {str(e)}")

    def execute_command_internal(self):
        """内部执行命令，不自动显示提示符"""
        self.current_cmd = self.current_cmd.strip()

        if self.current_cmd.startswith(('python', 'python3')):
            self.run_python_script()
            self.current_cmd = ""
            return

        # 处理其他命令...
        if self.current_cmd == "clear":
            self.terminal.clear()
        elif self.current_cmd.startswith("ls"):
            self.ls_command()
        elif self.current_cmd.startswith("cd"):
            self.cd_command()
        elif self.current_cmd == "pwd":
            self.pwd_command()
        elif self.current_cmd.startswith("touch"):
            self.touch_command()
        elif self.current_cmd.startswith("mkdir"):
            self.mkdir_command()
        elif self.current_cmd.startswith("rm"):
            self.rm_command()
        elif self.current_cmd.startswith("cat"):
            self.cat_command()
        elif self.current_cmd.startswith("cp"):
            self.cp_command()
        elif self.current_cmd.startswith("mv"):
            self.mv_command()
        elif self.current_cmd.startswith("echo"):
            self.echo_command()
        elif self.current_cmd.startswith("export"):
            self.export_command()
        elif self.current_cmd.startswith("head"):
            self.head_command()
        elif self.current_cmd.startswith("tail"):
            self.tail_command()
        elif self.current_cmd.startswith("grep"):
            self.grep_command()
        elif self.current_cmd.startswith("sort"):
            self.sort_command()
        elif self.current_cmd.startswith("uniq"):
            self.uniq_command()
        elif self.current_cmd.startswith("asciishow "):
            self.show_ascii_image()
        elif self.current_cmd.startswith("vim"):
            self.vim_command()
        elif self.current_cmd == "help":
            self.show_help()
        elif self.current_cmd == "exit":
            self.close()
        elif self.current_cmd.startswith("run"):
            script_path = self.current_cmd[4:].strip()
            self.run_script_file(script_path)
        else:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"pyterm: command not found: {self.current_cmd}")

    def run_python_script(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("python: missing script file")
            self.show_prompt()
            return

        script_path = parts[1]
        full_path = os.path.join(self.current_dir, script_path)

        if not os.path.exists(full_path):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"python: can't open file '{script_path}': [Errno 2] No such file or directory")
            self.show_prompt()
            return

        if not full_path.endswith('.py'):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"python: '{script_path}' is not a Python script file")
            self.show_prompt()
            return

        try:
            # 创建子进程执行Python脚本
            self.python_process = subprocess.Popen(
                [parts[0], full_path],
                cwd=self.current_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )

            threading.Thread(target=self.read_python_output, daemon=True).start()
            threading.Thread(target=self.read_python_errors, daemon=True).start()

            self.python_timeout_timer = QTimer(self)
            self.python_timeout_timer.setSingleShot(True)
            self.python_timeout_timer.timeout.connect(self.check_python_timeout)
            self.python_timeout_timer.start(30000)  # 30秒超时

            self.python_input_mode = True
            self.python_input_buffer = ""
            self.last_python_output = ""

        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"python: {str(e)}")
            self.show_prompt()

    def check_python_timeout(self):
        """检查Python进程是否超时"""
        if self.python_process and self.python_process.poll() is None:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("\n(python执行超时，强制终止)")
            self.python_process.terminate()
            try:
                self.python_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.python_process.kill()
            self.python_process = None
            self.python_input_mode = False
            self.show_prompt()

    def read_python_output(self):
        if not self.python_process or not self.python_process.stdout:
            return

        try:
            for line in iter(self.python_process.stdout.readline, ''):
                if line:
                    self.last_python_output = line.rstrip('\n')
                    self.terminal.setTextColor(QColor('#00FF00'))
                    self.terminal.append(self.last_python_output)
                    self.move_cursor_to_end()

                    # 重置超时计时器
                    if self.python_timeout_timer and self.python_timeout_timer.isActive():
                        self.python_timeout_timer.start(30000)
        except Exception as e:
            pass
        finally:
            # 进程结束时恢复状态
            if self.python_process:
                self.python_process.wait()
            self.python_process = None
            self.python_input_mode = False
            if self.python_timeout_timer and self.python_timeout_timer.isActive():
                self.python_timeout_timer.stop()
            if not self.current_cmd:  # 只有当没有等待执行的命令时才显示提示符
                self.show_prompt()

    def read_python_errors(self):
        """读取Python进程的错误输出"""
        if not self.python_process or not self.python_process.stderr:
            return

        try:
            for line in iter(self.python_process.stderr.readline, ''):
                if line:
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append(line.rstrip('\n'))
                    self.move_cursor_to_end()

                    # 重置超时计时器
                    if self.python_timeout_timer and self.python_timeout_timer.isActive():
                        self.python_timeout_timer.start(30000)
        except Exception as e:
            pass

    def handle_python_input(self, event):
        """处理Python脚本的交互式输入"""
        cursor = self.terminal.textCursor()

        # 阻止光标移动到输入行之前
        if cursor.position() < self.terminal.document().characterCount() - len(self.python_input_buffer):
            cursor.setPosition(self.terminal.document().characterCount())
            self.terminal.setTextCursor(cursor)

        # 处理Backspace键
        if event.key() == Qt.Key_Backspace:
            if self.python_input_buffer:
                cursor.deletePreviousChar()
                self.terminal.setTextCursor(cursor)
                self.python_input_buffer = self.python_input_buffer[:-1]
            return

        # 处理Enter键
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            # 将输入发送到Python进程
            if self.python_process and self.python_process.stdin:
                self.terminal.append('')  # 添加换行
                self.python_process.stdin.write(self.python_input_buffer + '\n')
                self.python_process.stdin.flush()
                self.python_input_buffer = ""
            return

        # 处理方向键
        elif event.key() == Qt.Key_Left:
            if cursor.position() > self.terminal.document().characterCount() - len(self.python_input_buffer):
                cursor.movePosition(QTextCursor.Left)
                self.terminal.setTextCursor(cursor)
            return
        elif event.key() == Qt.Key_Right:
            if cursor.position() < self.terminal.document().characterCount():
                cursor.movePosition(QTextCursor.Right)
                self.terminal.setTextCursor(cursor)
            return
        elif event.key() == Qt.Key_Up:
            # 历史命令导航
            if self.history:
                if self.history_index > 0:
                    self.history_index -= 1
                    self.replace_input(self.history[self.history_index])
            return
        elif event.key() == Qt.Key_Down:
            # 历史命令导航
            if self.history:
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    self.replace_input(self.history[self.history_index])
                elif self.history_index == len(self.history) - 1:
                    self.history_index += 1
                    self.replace_input("")
            return

        # 处理可打印字符
        text = event.text()
        if text:
            cursor.insertText(text)
            self.terminal.setTextCursor(cursor)
            self.python_input_buffer += text

    def replace_input(self, text):
        """替换当前输入内容"""
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(text)
        self.terminal.setTextCursor(cursor)
        self.python_input_buffer = text

    # === Linux命令实现 ===
    def ls_command(self):
        try:
            files = os.listdir(self.current_dir)
            filtered_files = [f for f in files if f not in ['__pycache__', '.idea']]
            for file in filtered_files:
                file_path = os.path.join(self.current_dir, file)
                if os.path.isdir(file_path):
                    self.terminal.setTextColor(QColor('#00BFFF'))
                    self.terminal.append(file + "/")
                else:
                    self.terminal.setTextColor(QColor('#00FF00'))
                    self.terminal.append(file)
        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"ls: {str(e)}")

    def cd_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            return

        target = parts[1]
        if target == "..":
            new_dir = os.path.dirname(self.current_dir)
        else:
            new_dir = os.path.join(self.current_dir, target)

        project_root = os.getcwd()
        if not os.path.abspath(new_dir).startswith(project_root):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("cd: permission denied (outside project directory)")
            return

        if os.path.isdir(new_dir):
            self.current_dir = new_dir
        else:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"cd: no such directory: {target}")

    def pwd_command(self):
        rel_path = os.path.relpath(self.current_dir, os.getcwd())
        self.terminal.setTextColor(QColor('#00FF00'))
        self.terminal.append(rel_path)

    def touch_command(self):
        parts = self.current_cmd.split()[1:]
        for filename in parts:
            file_path = os.path.join(self.current_dir, filename)
            try:
                with open(file_path, 'a', encoding="utf-8"):
                    pass
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(f"created: {filename}")
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"touch: {str(e)}")

    def mkdir_command(self):
        parts = self.current_cmd.split()[1:]
        for dirname in parts:
            dir_path = os.path.join(self.current_dir, dirname)
            try:
                os.makedirs(dir_path, exist_ok=True)
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(f"created directory: {dirname}")
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"mkdir: {str(e)}")

    def rm_command(self):
        parts = self.current_cmd.split()[1:]
        for path in parts:
            full_path = os.path.join(self.current_dir, path)
            try:
                if os.path.isfile(full_path):
                    os.remove(full_path)
                    self.terminal.append(f"removed: {path}")
                elif os.path.isdir(full_path):
                    os.rmdir(full_path)
                    self.terminal.append(f"removed directory: {path}")
                else:
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append(f"rm: no such file or directory: {path}")
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"rm: {str(e)}")

    def cat_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("cat: missing operand")
            return

        for filename in parts[1:]:
            file_path = os.path.join(self.current_dir, filename)
            try:
                if not os.path.exists(file_path):
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append(f"cat: {filename}: No such file or directory")
                    continue

                if os.path.isdir(file_path):
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append(f"cat: {filename}: Is a directory")
                    continue

                with open(file_path, 'r', encoding="utf-8") as f:
                    content = f.read()
                    self.terminal.setTextColor(QColor('#00FF00'))
                    self.terminal.append(content)
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"cat: {filename}: {str(e)}")

    def cp_command(self):
        parts = self.current_cmd.split()[1:]
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("cp: missing file operand")
            return

        src = parts[0]
        dst = parts[1]

        src_path = os.path.join(self.current_dir, src)
        dst_path = os.path.join(self.current_dir, dst)

        if not os.path.exists(src_path):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"cp: cannot stat '{src}': No such file or directory")
            return

        if os.path.isdir(src_path):
            if len(parts) > 2 or not dst.endswith('/'):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"cp: omitting directory '{src}'")
                return

            os.makedirs(dst_path, exist_ok=True)

            for item in os.listdir(src_path):
                item_src = os.path.join(src_path, item)
                item_dst = os.path.join(dst_path, item)

                if os.path.isdir(item_src):
                    os.makedirs(item_dst, exist_ok=True)
                else:
                    with open(item_src, 'r', encoding="utf-8") as f_src:
                        content = f_src.read()
                    with open(item_dst, 'w', encoding="utf-8") as f_dst:
                        f_dst.write(content)

            self.terminal.setTextColor(QColor('#00FF00'))
            self.terminal.append(f"copied directory '{src}' to '{dst}'")
        else:
            try:
                with open(src_path, 'r', encoding="utf-8") as f_src:
                    content = f_src.read()

                if os.path.isdir(dst_path):
                    dst_path = os.path.join(dst_path, os.path.basename(src_path))

                with open(dst_path, 'w', encoding="utf-8") as f_dst:
                    f_dst.write(content)

                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(f"copied '{src}' to '{dst}'")
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"cp: error copying file: {str(e)}")

    def mv_command(self):
        parts = self.current_cmd.split()[1:]
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("mv: missing file operand")
            return

        src = parts[0]
        dst = parts[1]

        src_path = os.path.join(self.current_dir, src)
        dst_path = os.path.join(self.current_dir, dst)

        if not os.path.exists(src_path):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"mv: cannot stat '{src}': No such file or directory")
            return

        try:
            if os.path.isdir(dst_path):
                dst_path = os.path.join(dst_path, os.path.basename(src_path))

            os.replace(src_path, dst_path)
            self.terminal.setTextColor(QColor('#00FF00'))
            self.terminal.append(f"moved '{src}' to '{dst}'")
        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"mv: error moving file: {str(e)}")

    def echo_command(self):
        text = self.current_cmd[5:].strip()

        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            quote_char = text[0]
            content = text[1:-1]
            content = re.sub(r'\$(\w+)', lambda m: self.environment.get(m.group(1), ''), content)
            content = content.replace(f'\\{quote_char}', quote_char)
            content = content.replace(r'\\', '\\')
        else:
            content = re.sub(r'\$(\w+)', lambda m: self.environment.get(m.group(1), ''), text)

        self.terminal.setTextColor(QColor('#00FF00'))
        self.terminal.append(content)

    def export_command(self):
        parts = self.current_cmd.split()[1:]
        if not parts:
            for key, value in self.environment.items():
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(f"{key}={value}")
            return

        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                self.environment[key] = value
            else:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"export: '{part}': not a valid identifier")

    def head_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("head: missing operand")
            return

        n_lines = 10
        filename = None
        i = 1

        while i < len(parts):
            part = parts[i]
            if part.startswith('-n'):
                if len(part) == 2:
                    if i + 1 >= len(parts):
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append("head: missing number of lines after -n")
                        return
                    try:
                        n_lines = int(parts[i + 1])
                        i += 1
                    except ValueError:
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append(f"head: invalid number of lines: '{parts[i + 1]}'")
                        return
                else:
                    try:
                        n_lines = int(part[2:])
                    except ValueError:
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append(f"head: invalid number of lines: '{part[2:]}'")
                        return
            else:
                filename = part
                break

            i += 1

        if not filename:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("head: missing file operand")
            return

        file_path = os.path.join(self.current_dir, filename)

        try:
            if not os.path.exists(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"head: {filename}: No such file or directory")
                return

            if os.path.isdir(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"head: {filename}: Is a directory")
                return

            with open(file_path, 'r', encoding="utf-8") as f:
                lines = f.readlines()[:n_lines]
                content = ''.join(lines)
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(content)
        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"head: {filename}: {str(e)}")

    def tail_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("tail: missing operand")
            return

        n_lines = 10
        filename = None
        follow = False
        i = 1

        while i < len(parts):
            part = parts[i]
            if part == '-f':
                follow = True
            elif part.startswith('-n'):
                if len(part) == 2:
                    if i + 1 >= len(parts):
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append("tail: missing number of lines after -n")
                        return
                    try:
                        n_lines = int(parts[i + 1])
                        i += 1
                    except ValueError:
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append(f"tail: invalid number of lines: '{parts[i + 1]}'")
                        return
                else:
                    try:
                        n_lines = int(part[2:])
                    except ValueError:
                        self.terminal.setTextColor(QColor('#FF0000'))
                        self.terminal.append(f"tail: invalid number of lines: '{part[2:]}'")
                        return
            else:
                filename = part
                break

            i += 1

        if not filename:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("tail: missing file operand")
            return

        file_path = os.path.join(self.current_dir, filename)

        try:
            if not os.path.exists(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"tail: {filename}: No such file or directory")
                return

            if os.path.isdir(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"tail: {filename}: Is a directory")
                return

            with open(file_path, 'r', encoding="utf-8") as f:
                lines = f.readlines()
                content = ''.join(lines[-n_lines:])
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(content)

            if follow:
                self.terminal.setTextColor(QColor('#FFFF00'))
                self.terminal.append("(simulated) tail: following file - use Ctrl+C to stop")
        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"tail: {filename}: {str(e)}")

    def grep_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 3:
            if len(parts) == 2:
                if os.path.exists(os.path.join(self.current_dir, parts[1])):
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append("grep: missing pattern operand")
                else:
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append("grep: missing file operand")
            else:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append("grep: missing pattern and file operands")
            return

        options = []
        i = 1

        while i < len(parts) and parts[i].startswith('-'):
            options.extend(parts[i][1:])
            i += 1

        if i >= len(parts):
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("grep: missing pattern and file operands")
            return

        pattern = parts[i]
        i += 1
        files = parts[i:]

        if not files:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("grep: missing file operand")
            return

        ignore_case = 'i' in options
        try:
            flags = re.IGNORECASE if ignore_case else 0
            regex = re.compile(pattern, flags)
        except re.error as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"grep: invalid regular expression: {str(e)}")
            return

        found = False
        for filename in files:
            file_path = os.path.join(self.current_dir, filename)

            try:
                if not os.path.exists(file_path):
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append(f"grep: {filename}: No such file or directory")
                    continue

                if os.path.isdir(file_path):
                    self.terminal.setTextColor(QColor('#FF0000'))
                    self.terminal.append(f"grep: {filename}: Is a directory")
                    continue

                with open(file_path, 'r', encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            self.terminal.setTextColor(QColor('#00FF00'))
                            if len(files) > 1:
                                self.terminal.append(f"{filename}:")

                            # 手动处理高亮显示，使用[[]]框住匹配内容
                            result = ""
                            last_end = 0
                            for match in regex.finditer(line):
                                start, end = match.span()
                                result += line[last_end:start]
                                result += f"[[{line[start:end]}]]"
                                last_end = end
                            result += line[last_end:]

                            output = f"{line_num}: {result.rstrip('\n')}"
                            self.terminal.append(output)
                            found = True
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"grep: {filename}: {str(e)}")

        if not found and all(os.path.exists(os.path.join(self.current_dir, f)) for f in files):
            self.terminal.setTextColor(QColor('#00FF00'))
            self.terminal.append("(no matches found)")

    def sort_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("sort: missing operand")
            return

        filename = parts[1]
        file_path = os.path.join(self.current_dir, filename)

        try:
            if not os.path.exists(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"sort: {filename}: No such file or directory")
                return

            if os.path.isdir(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"sort: {filename}: Is a directory")
                return

            with open(file_path, 'r', encoding="utf-8") as f:
                lines = f.readlines()
                sorted_lines = sorted(lines)
                content = ''.join(sorted_lines)
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(content)
        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"sort: {filename}: {str(e)}")

    def uniq_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("uniq: missing operand")
            return

        filename = parts[1]
        file_path = os.path.join(self.current_dir, filename)

        try:
            if not os.path.exists(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"uniq: {filename}: No such file or directory")
                return

            if os.path.isdir(file_path):
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"uniq: {filename}: Is a directory")
                return

            with open(file_path, 'r', encoding="utf-8") as f:
                lines = f.readlines()
                unique_lines = []
                prev_line = None

                for line in lines:
                    if line != prev_line:
                        unique_lines.append(line)
                        prev_line = line

                content = ''.join(unique_lines)
                self.terminal.setTextColor(QColor('#00FF00'))
                self.terminal.append(content)
        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"uniq: {filename}: {str(e)}")

    def show_ascii_image(self):
        path = self.current_cmd[9:].strip()
        full_path = os.path.join(self.current_dir, path)

        try:
            my_art = CustomAsciiArt.from_image(full_path)
            ascii_text = my_art.to_ascii(
                columns=40,
                width_ratio=2.0,
                monochrome=True,
            )

            self.terminal.setTextColor(QColor('#00ff00'))
            self.terminal.append(ascii_text)

        except Exception as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"错误: 无法显示ASCII图片 - {str(e)}")

    def curl_command(self):
        try:
            url = self.current_cmd.split(' ', 1)[1].strip()
            response = requests.get(url, timeout=10)
            response.encoding = response.apparent_encoding
            response.raise_for_status()
            escaped_text = escape(response.text)
            self.terminal.setTextColor(QColor('#00FF00'))
            self.terminal.append(escaped_text)
        except IndexError:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("curl: Please provide a URL.")
        except requests.RequestException as e:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append(f"curl: Error: {str(e)}")
        except Exception:
            traceback.print_exc()

    # === Vim编辑器集成 ===
    def vim_command(self):
        parts = self.current_cmd.split()
        if len(parts) < 2:
            self.terminal.setTextColor(QColor('#FF0000'))
            self.terminal.append("vim: missing filename")
            return

        filename = parts[1]
        file_path = os.path.join(self.current_dir, filename)

        self.vim_editor = VimEditor(self.terminal, self.current_dir, filename)

        success = self.vim_editor.load_file(file_path)
        if not success:
            self.vim_editor = None
            return

        self.terminal.clear()
        self.render_vim_editor()

    def render_vim_editor(self):
        if self.vim_editor and self.vim_editor.is_active:
            self.vim_editor.render()

    def exit_vim_editor(self):
        if self.vim_editor:
            self.vim_editor = None
            self.terminal.clear()
            self.show_prompt()

    # === 关键修复：处理按键事件 ===
    def handle_key_press(self, event):
        if not self.current_prompt_block:
            return

        cursor = self.terminal.textCursor()
        prompt_start = self.current_prompt_block.position()
        current_pos = cursor.position()

        if current_pos < prompt_start + len(self.current_prompt):
            cursor.setPosition(prompt_start + len(self.current_prompt))
            self.terminal.setTextCursor(cursor)
            current_pos = prompt_start + len(self.current_prompt)

        if event.key() == Qt.Key_Backspace:
            if current_pos > prompt_start + len(self.current_prompt):
                cursor.deletePreviousChar()
                self.terminal.setTextCursor(cursor)
                self.current_cmd = self.get_current_command_text()
            return

        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.current_cmd = self.get_current_command_text()
            self.handle_enter()
            return

        elif event.key() == Qt.Key_Up:
            self.navigate_history(-1)
            return
        elif event.key() == Qt.Key_Down:
            self.navigate_history(1)
            return
        elif event.key() == Qt.Key_Left:
            if current_pos > prompt_start + len(self.current_prompt):
                cursor.movePosition(QTextCursor.Left)
                self.terminal.setTextCursor(cursor)
            return
        elif event.key() == Qt.Key_Right:
            if current_pos < self.terminal.document().characterCount():
                cursor.movePosition(QTextCursor.Right)
                self.terminal.setTextCursor(cursor)
            return

        text = event.text()
        if text.isprintable():
            cursor.insertText(text)
            self.terminal.setTextCursor(cursor)
            self.current_cmd = self.get_current_command_text()

    def navigate_history(self, direction):
        if not self.history:
            return

        if direction == -1:
            if self.history_index == len(self.history):
                self.saved_cmd = self.current_cmd
            if self.history_index > 0:
                self.history_index -= 1
        else:
            if self.history_index < len(self.history):
                self.history_index += 1

        cmd = ""
        if 0 <= self.history_index < len(self.history):
            cmd = self.history[self.history_index]
        elif self.history_index == len(self.history):
            cmd = self.saved_cmd if hasattr(self, 'saved_cmd') else ""

        self.update_command_line(cmd)

    def update_command_line(self, cmd):
        cursor = QTextCursor(self.current_prompt_block)
        cursor.setPosition(self.current_prompt_block.position() + len(self.current_prompt))
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(cmd)
        self.current_cmd = cmd
        self.move_cursor_to_end()

    def handle_enter(self):
        self.execute_command()
        self.history_index = len(self.history)

    def get_current_command_text(self):
        cursor = QTextCursor(self.current_prompt_block)
        cursor.setPosition(self.current_prompt_block.position() + len(self.current_prompt))
        cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
        return cursor.selectedText()

    def show_help(self):
        help_text = """
        PyTerminal v0.9 帮助信息

        以下是支持的命令列表：
        - clear: 清空终端屏幕
        - ls: 列出当前目录下的文件和文件夹
        - cd [目录名]: 切换当前工作目录
        - pwd: 显示当前工作目录的路径
        - touch [文件名]: 创建一个新的空文件
        - mkdir [目录名]: 创建一个新的目录
        - rm [文件名/目录名]: 删除文件或目录
        - cat [文件名]: 显示文件内容
        - cp [源文件/目录] [目标文件/目录]: 复制文件或目录
        - mv [源文件/目录] [目标文件/目录]: 移动或重命名文件或目录
        - echo [文本]: 在终端输出文本
        - export [变量名]=[值]: 设置环境变量
        - head -n [行数] [文件名]: 显示文件的前几行
        - tail -n [行数] [文件名]: 显示文件的后几行
        - grep [文件名]: 在文件中搜索匹配的文本
        - sort [文件名]: 对文件内容进行排序
        - uniq [文件名]: 去除文件中的重复行
        - asciishow [图片路径]: 显示 ASCII 艺术图片
        - vim [文件名]: 打开 Vim 编辑器编辑文件
            - 正常模式: 进入 Vim 默认处于此模式，可进行光标移动、进入其他模式等操作。常用命令有：
                - i: 进入插入模式
                - : 进入命令模式
                - h/j/k/l: 分别向左/下/上/右移动光标
                - G: 移到文件末尾
                - gg: 移到文件开头
            - 插入模式: 用于输入和编辑文本。可使用方向键移动光标，按 Enter 插入新行，按 Backspace 删除字符。
            - 命令模式: 用于执行保存、退出等操作。常用命令有：
                - w: 保存文件
                - q: 退出编辑器（若文件有修改需先保存）
                - q!: 强制退出编辑器
                - wq 或 x: 保存并退出编辑器
        - help: 显示帮助信息
        - exit: 关闭终端
        - curl [URL]: 发送 HTTP 请求并显示响应
        - run [脚本路径]: 运行指定的 shell 脚本
            - 脚本需以 .sh 结尾。脚本支持以下常见语法：
                - 变量赋值: 如 a=5 ，可通过 $a 引用变量。
                - 函数定义: 使用 `def 函数名(参数列表) { 函数体 }` 定义函数，在函数内部可使用 `local` 定义局部变量，`return` 返回值。
                - 条件语句: 如 `if [ 条件 ]; ... else ... fi` ，根据条件执行不同代码块。
                - 循环语句: 如 `while [ 条件 ]; ... done` ，当条件为真时循环执行代码块。
            - 参考example.sh。
        - python/python3 [脚本路径]: 运行 Python 脚本
        """
        self.terminal.setTextColor(QColor('#00FF00'))
        self.terminal.append(help_text)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    terminal = TerminalEmulator()
    terminal.show()
    print("Server running...")
    sys.exit(app.exec_())