import os

from PyQt5.QtCore import *
from PyQt5.QtGui import *


class VimEditor:
    def __init__(self, terminal_widget, current_dir, filename):
        self.terminal = terminal_widget
        self.current_dir = current_dir
        self.filename = filename
        self.is_active = True
        self.edit_buffer = []
        self.vim_mode = "normal"
        self.vim_cursor = [0, 0]
        self.current_cmd = ""
        self.status_message = ""
        self.status_message_timeout = 0
        self.original_content = None  # 保存原始内容用于判断修改

    def load_file(self, file_path):
        # 读取文件内容到缓冲区
        self.edit_buffer = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r') as f:
                    self.edit_buffer = [line.rstrip('\n') for line in f.readlines()]
                # 保存原始内容用于判断文件是否被修改
                self.original_content = self.edit_buffer.copy()
                return True
            except Exception as e:
                self.terminal.setTextColor(QColor('#FF0000'))
                self.terminal.append(f"vim: cannot open file: {str(e)}")
                return False
        else:
            # 文件不存在，创建空缓冲区
            self.edit_buffer = [""]
            self.original_content = [""]
            return True

    def render(self):
        self.terminal.clear()

        # 显示文件内容
        self.terminal.setTextColor(QColor('#00FF00'))
        for line in self.edit_buffer:
            self.terminal.append(line)

        # 显示状态栏
        status_line = f"-- {self.vim_mode.upper()} -- {self.filename}"
        if self.status_message:
            status_line += f"  {self.status_message}"

        self.terminal.setTextColor(QColor('#FFFF00'))  # 黄色状态栏
        self.terminal.append(status_line)

        # 设置光标位置
        cursor = self.terminal.textCursor()
        if self.edit_buffer:
            # 计算光标位置
            char_pos = sum(len(line) + 1 for line in self.edit_buffer[:self.vim_cursor[0]])
            char_pos += self.vim_cursor[1]
            cursor.setPosition(char_pos)
        else:
            cursor.setPosition(0)
        self.terminal.setTextCursor(cursor)

        # 如果有状态消息超时，重置它
        if self.status_message_timeout > 0:
            self.status_message_timeout -= 1
            if self.status_message_timeout == 0:
                self.status_message = ""

    def handle_key_press(self, event):
        key = event.key()
        text = event.text()

        # 处理Escape键返回正常模式
        if key == Qt.Key_Escape:
            self.vim_mode = "normal"
            self.current_cmd = ""
            self.render()
            return

        # 命令模式
        if self.vim_mode == "command":
            if key == Qt.Key_Return:
                self.execute_command()
            elif key == Qt.Key_Backspace:
                if self.current_cmd:
                    self.current_cmd = self.current_cmd[:-1]
                    self.render()
            elif text.isprintable():
                self.current_cmd += text
                self.render()
            return

        # 正常模式
        if self.vim_mode == "normal":
            if text == 'i':
                self.vim_mode = "insert"
                self.render()
            elif text == ':':
                self.vim_mode = "command"
                self.current_cmd = ""
                self.render()
            elif text == 'h':  # 左移
                if self.vim_cursor[1] > 0:
                    self.vim_cursor[1] -= 1
                    self.render()
            elif text == 'j':  # 下移
                if self.vim_cursor[0] < len(self.edit_buffer) - 1:
                    self.vim_cursor[0] += 1
                    self.render()
            elif text == 'k':  # 上移
                if self.vim_cursor[0] > 0:
                    self.vim_cursor[0] -= 1
                    self.render()
            elif text == 'l':  # 右移
                if self.vim_cursor[1] < len(self.edit_buffer[self.vim_cursor[0]]):
                    self.vim_cursor[1] += 1
                    self.render()
            elif text == 'G':  # 移到文件末尾
                if self.edit_buffer:
                    self.vim_cursor = [len(self.edit_buffer) - 1, 0]
                    self.render()
            elif text == 'gg':  # 移到文件开头
                self.vim_cursor = [0, 0]
                self.render()
            return

        # 插入模式
        if self.vim_mode == "insert":
            if key == Qt.Key_Return:
                # 插入新行
                current_line = self.vim_cursor[0]
                current_col = self.vim_cursor[1]
                line_text = self.edit_buffer[current_line]

                # 分割行
                self.edit_buffer[current_line] = line_text[:current_col]
                self.edit_buffer.insert(current_line + 1, line_text[current_col:])

                # 更新光标位置
                self.vim_cursor = [current_line + 1, 0]
                self.render()
            elif key == Qt.Key_Backspace:
                current_line = self.vim_cursor[0]
                current_col = self.vim_cursor[1]

                if current_col > 0:
                    # 删除当前字符
                    line_text = self.edit_buffer[current_line]
                    self.edit_buffer[current_line] = line_text[:current_col - 1] + line_text[current_col:]
                    self.vim_cursor[1] -= 1
                    self.render()
                elif current_line > 0:
                    # 合并到上一行
                    prev_line = current_line - 1
                    prev_line_text = self.edit_buffer[prev_line]
                    current_line_text = self.edit_buffer[current_line]

                    self.edit_buffer[prev_line] = prev_line_text + current_line_text
                    self.edit_buffer.pop(current_line)

                    # 更新光标位置
                    self.vim_cursor = [prev_line, len(prev_line_text)]
                    self.render()
            elif key == Qt.Key_Left:
                if self.vim_cursor[1] > 0:
                    self.vim_cursor[1] -= 1
                    self.render()
            elif key == Qt.Key_Right:
                current_line = self.vim_cursor[0]
                if self.vim_cursor[1] < len(self.edit_buffer[current_line]):
                    self.vim_cursor[1] += 1
                    self.render()
            elif key == Qt.Key_Up:
                if self.vim_cursor[0] > 0:
                    self.vim_cursor[0] -= 1
                    # 确保列位置不超过新行的长度
                    current_line = self.vim_cursor[0]
                    self.vim_cursor[1] = min(self.vim_cursor[1], len(self.edit_buffer[current_line]))
                    self.render()
            elif key == Qt.Key_Down:
                if self.vim_cursor[0] < len(self.edit_buffer) - 1:
                    self.vim_cursor[0] += 1
                    # 确保列位置不超过新行的长度
                    current_line = self.vim_cursor[0]
                    self.vim_cursor[1] = min(self.vim_cursor[1], len(self.edit_buffer[current_line]))
                    self.render()
            elif text.isprintable():
                # 插入字符
                current_line = self.vim_cursor[0]
                current_col = self.vim_cursor[1]

                # 确保缓冲区不为空
                if not self.edit_buffer:
                    self.edit_buffer = [""]

                # 确保当前行索引有效
                if current_line >= len(self.edit_buffer):
                    # 添加空行直到达到所需的行数
                    while current_line >= len(self.edit_buffer):
                        self.edit_buffer.append("")

                line_text = self.edit_buffer[current_line]

                # 插入字符
                self.edit_buffer[current_line] = line_text[:current_col] + text + line_text[current_col:]
                self.vim_cursor[1] += 1
                self.render()

    def execute_command(self):
        cmd = self.current_cmd.strip()

        if cmd == "w":  # 保存
            self.save_file()
        elif cmd == "q":  # 退出
            if self.is_file_modified():
                self.status_message = "E37: No write since last change (add ! to override)"
                self.status_message_timeout = 100  # 约2秒
            else:
                self.is_active = False  # 标记编辑器为非活动状态
        elif cmd == "q!":  # 强制退出
            self.is_active = False  # 标记编辑器为非活动状态
        elif cmd == "wq" or cmd == "x":  # 保存并退出
            self.save_file()
            if not self.status_message.startswith("E"):  # 如果保存成功
                self.is_active = False  # 标记编辑器为非活动状态
        else:
            self.status_message = f"E492: Not an editor command: {cmd}"
            self.status_message_timeout = 100

        self.vim_mode = "normal"
        self.current_cmd = ""
        self.render()

    def save_file(self):
        file_path = os.path.join(self.current_dir, self.filename)
        try:
            with open(file_path, 'w') as f:
                for line in self.edit_buffer:
                    f.write(line + '\n')
            # 保存后更新原始内容
            self.original_content = self.edit_buffer.copy()
            self.status_message = f'"{self.filename}" {len(self.edit_buffer)}L, {sum(len(line) for line in self.edit_buffer)}C written'
            self.status_message_timeout = 100
        except Exception as e:
            self.status_message = f"E502: Could not write file: {str(e)}"
            self.status_message_timeout = 100

    def is_file_modified(self):
        # 检查文件是否被修改
        if self.original_content is None:
            return False

        if len(self.original_content) != len(self.edit_buffer):
            return True

        for i in range(len(self.original_content)):
            if self.original_content[i] != self.edit_buffer[i]:
                return True

        return False