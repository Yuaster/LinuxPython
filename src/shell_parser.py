import re
import shlex


class ShellParser:
    def __init__(self, terminal):
        self.terminal = terminal
        self.variables = {}
        self.loop_stack = []
        self.if_stack = []
        self.in_function = False
        self.functions = {}
        self.command_sub_re = re.compile(r'\$\(((?:[^()]|\([^()]*\))*)\)|\$\{(\w+)\}|\$(\w+)')
        self.arithmetic_re = re.compile(r'\$\(\((.*?)\)\)')
        print("ShellParser 初始化完成")

    def parse(self, script_content, context_dir):
        """解析并执行Shell脚本内容"""
        self.context_dir = context_dir
        lines = script_content.split('\n')
        line_num = 0

        # 标记脚本执行状态，避免内部命令进入历史记录
        self.terminal.is_script_execution = True
        print(f"开始解析脚本，上下文目录: {context_dir}")

        try:
            while line_num < len(lines):
                line = lines[line_num].rstrip('\n')  # 保留行首空格，移除行尾换行符
                stripped_line = line.strip()
                line_num += 1
                print(f"正在处理第 {line_num - 1} 行: {line}")

                # 空行或注释
                if not stripped_line or stripped_line.startswith('#'):
                    print("跳过空行或注释")
                    continue

                # 函数定义（使用def关键字）
                func_def_match = re.match(r'^def (\w+)\(\s*([\w,\s]*)\s*\)\s*\{', stripped_line)
                if func_def_match:
                    func_name = func_def_match.group(1)
                    params = [p.strip() for p in func_def_match.group(2).split(',') if p.strip()]
                    self.in_function = True
                    self.functions[func_name] = {
                        'params': params,
                        'lines': []
                    }
                    print(f"进入函数定义: {func_name}，参数: {params}")
                    continue

                if stripped_line.startswith('}') and self.in_function:
                    self.in_function = False
                    print("函数定义结束")
                    continue

                if self.in_function:
                    func_name = list(self.functions.keys())[-1]
                    self.functions[func_name]['lines'].append(line)
                    continue

                # local 语句处理（保持原有逻辑不变）
                if stripped_line.startswith('local '):
                    if not self.in_function:
                        print("local 语句只能在函数内部使用")
                        continue
                    parts = stripped_line[6:].strip().split('=', 1)
                    if len(parts) == 2:
                        var_name = parts[0].strip()
                        var_value = parts[1].strip()
                        var_value = self._substitute_arithmetic(var_value)
                        var_value = self._substitute_variables(var_value)
                        func_name = list(self.functions.keys())[-1]
                        if 'local_vars' not in self.functions[func_name]:
                            self.functions[func_name]['local_vars'] = {}
                        self.functions[func_name]['local_vars'][var_name] = var_value
                        print(f"函数 {func_name} 内局部变量 {var_name} 赋值为: {var_value}")
                    continue

                # return 语句处理（保持原有逻辑不变）
                if stripped_line.startswith('return '):
                    if not self.in_function:
                        print("return 语句只能在函数内部使用")
                        continue
                    return_value = stripped_line[7:].strip()
                    return_value = self._substitute_arithmetic(return_value)
                    return_value = self._substitute_variables(return_value)
                    func_name = list(self.functions.keys())[-1]
                    self.functions[func_name]['return_value'] = return_value
                    self.in_function = False
                    print(f"函数 {func_name} 返回值: {return_value}")
                    return return_value

                # 变量赋值（增加函数调用处理）
                var_match = re.match(r'^(\w+)\s*=\s*(.*)$', stripped_line)
                if var_match:
                    var_name = var_match.group(1)
                    var_value = var_match.group(2).strip()
                    print(f"检测到变量赋值: {var_name} = {var_value}")

                    # 检测函数调用
                    func_call_match = re.match(r'\$\((\w+)\(\s*([\w,\s]*)\s*\)\)', var_value)
                    if func_call_match:
                        func_name = func_call_match.group(1)
                        args = [p.strip() for p in func_call_match.group(2).split(',') if p.strip()]
                        if func_name in self.functions:
                            func_info = self.functions[func_name]
                            if len(args) != len(func_info['params']):
                                print(f"函数 {func_name} 参数数量不匹配")
                                var_value = ""
                            else:
                                # 创建新的执行上下文
                                exec_context = {
                                    'variables': self.variables.copy(),  # 继承全局变量
                                    'local_vars': {},  # 局部变量
                                    'return_value': None  # 返回值
                                }

                                # 绑定参数到局部变量
                                for param, arg in zip(func_info['params'], args):
                                    # 处理参数值中的变量和算术扩展
                                    processed_arg = self._substitute_arithmetic(arg)
                                    processed_arg = self._substitute_variables(processed_arg)

                                    exec_context['local_vars'][param] = processed_arg
                                    print(f"绑定参数 {param} = {processed_arg}")

                                # 执行函数体
                                return_value = self._execute_function(func_info, exec_context)

                                if return_value is not None:
                                    var_value = return_value
                                    print(f"函数 {func_name} 返回值: {return_value}")
                        else:
                            print(f"未定义的函数: {func_name}")
                            var_value = ""
                    else:
                        # 处理算术扩展
                        var_value = self._substitute_arithmetic(var_value)

                        # 处理引号
                        if var_value.startswith(('"', "'")):
                            quote_char = var_value[0]
                            var_value = var_value[1:]  # 移除开头的引号
                            print(f"处理带引号的值，引号字符: {quote_char}")

                            # 查找匹配的引号（支持转义）
                            end_quote_pos = -1
                            escaped = False
                            for i, c in enumerate(var_value):
                                if c == '\\' and not escaped:
                                    escaped = True
                                    continue
                                if c == quote_char and not escaped:
                                    end_quote_pos = i
                                    break
                                escaped = False

                            if end_quote_pos != -1:
                                value_content = var_value[:end_quote_pos]
                                # 处理转义字符
                                value_content = value_content.replace('\\n', '\n')
                                value_content = value_content.replace('\\t', '\t')
                                value_content = value_content.replace('\\\\', '\\')
                                value_content = value_content.replace(f'\\{quote_char}', quote_char)

                                # 双引号内进行变量替换
                                if quote_char == '"':
                                    value_content = self._substitute_variables(value_content)

                                var_value = value_content
                            else:
                                # 未找到匹配的引号 - 错误处理
                                var_value = var_value.rstrip(quote_char)
                        else:
                            # 无引号的普通字符串
                            var_value = self._substitute_variables(var_value)

                    self.variables[var_name] = var_value
                    print(f"变量 {var_name} 赋值为: {var_value}")
                    continue

                # 分支结构（保持原有逻辑不变）
                if stripped_line.startswith('if '):
                    condition = stripped_line[3:].strip()
                    should_execute = self._evaluate_condition(condition)
                    self.if_stack.append({
                        'condition': condition,
                        'executed': should_execute,
                        'else_pos': None
                    })
                    if should_execute:
                        print(f"if 条件 {condition} 为真，执行分支")
                    else:
                        while line_num < len(lines):
                            next_line = lines[line_num].strip()
                            if next_line.startswith(('elif ', 'else', 'fi')):
                                break
                            line_num += 1
                        print(f"if 条件 {condition} 为假，跳过分支")
                    continue

                if stripped_line.startswith('elif '):
                    if not self.if_stack:
                        print("无效的 elif 语句，跳过")
                        continue

                    if self.if_stack[-1]['executed']:
                        # 跳过已执行分支
                        while line_num < len(lines) and not lines[line_num].strip().startswith('fi'):
                            line_num += 1
                        print("跳过已执行的 elif 分支")
                        continue

                    condition = stripped_line[5:].strip()
                    should_execute = self._evaluate_condition(condition)

                    if should_execute:
                        self.if_stack[-1]['executed'] = True
                        print(f"elif 条件 {condition} 为真，执行分支")
                    else:
                        # 跳过此分支
                        while line_num < len(lines):
                            next_line = lines[line_num].strip()
                            if next_line.startswith('fi'):
                                break
                            line_num += 1
                        print(f"elif 条件 {condition} 为假，跳过分支")
                    continue

                if stripped_line.startswith('else'):
                    if not self.if_stack:
                        print("无效的 else 语句，跳过")
                        continue

                    if self.if_stack[-1]['executed']:
                        # 跳过else块
                        while line_num < len(lines):
                            next_line = lines[line_num].strip()
                            if next_line.startswith('fi'):
                                break
                            line_num += 1
                        print("跳过已执行的 else 块")
                        continue

                    self.if_stack[-1]['executed'] = True
                    print("进入 else 块")
                    continue

                if stripped_line.startswith('fi'):
                    if not self.if_stack:
                        print("无效的 fi 语句，跳过")
                        continue
                    self.if_stack.pop()
                    print("结束 if 语句块")
                    continue

                # 循环结构（保持原有逻辑不变）
                if stripped_line.startswith('while '):
                    condition = stripped_line[6:].strip()
                    loop_start = line_num - 1
                    self.loop_stack.append({
                        'condition': condition,
                        'start_line': loop_start
                    })
                    should_execute = self._evaluate_condition(condition)
                    if not should_execute:
                        # 跳过循环体
                        while line_num < len(lines) and not lines[line_num].strip().startswith('done'):
                            line_num += 1
                        self.loop_stack.pop()
                        print(f"while 条件 {condition} 为假，跳过循环体")
                    continue

                if stripped_line.startswith('done'):
                    if not self.loop_stack:
                        print("无效的 done 语句，跳过")
                        continue
                    loop_info = self.loop_stack[-1]
                    condition = loop_info['condition']
                    start_line = loop_info['start_line']
                    should_execute = self._evaluate_condition(condition)
                    if should_execute:
                        line_num = start_line + 1  # 回到循环开始处
                        print(f"while 条件 {condition} 为真，继续循环")
                    else:
                        self.loop_stack.pop()
                        print(f"while 条件 {condition} 为假，结束循环")
                    continue

                # 函数调用（修改为使用独立上下文执行函数体）
                func_call_match = re.match(r'^(\w+)\(\s*([\w,\s]*)\s*\)$', stripped_line)
                if func_call_match:
                    func_name = func_call_match.group(1)
                    args = [p.strip() for p in func_call_match.group(2).split(',') if p.strip()]
                    if func_name in self.functions:
                        func_info = self.functions[func_name]
                        if len(args) != len(func_info['params']):
                            print(f"函数 {func_name} 参数数量不匹配")
                            continue

                        # 创建新的执行上下文
                        exec_context = {
                            'variables': self.variables.copy(),  # 继承全局变量
                            'local_vars': {},  # 局部变量
                            'return_value': None  # 返回值
                        }

                        # 绑定参数到局部变量
                        for param, arg in zip(func_info['params'], args):
                            # 处理参数值中的变量和算术扩展
                            processed_arg = self._substitute_arithmetic(arg)
                            processed_arg = self._substitute_variables(processed_arg)

                            exec_context['local_vars'][param] = processed_arg
                            print(f"绑定参数 {param} = {processed_arg}")

                        # 执行函数体
                        return_value = self._execute_function(func_info, exec_context)

                        if return_value is not None:
                            self.variables[f'${func_name}'] = return_value
                            print(f"函数 {func_name} 返回值: {return_value}")
                    else:
                        print(f"未定义的函数: {func_name}")
                    continue

                # 命令执行（保持原有逻辑不变）
                processed_line = self._substitute_variables(line)
                processed_line = self._substitute_commands(processed_line)
                self.terminal.current_cmd = processed_line
                print(f"执行命令: {processed_line}")
                self.terminal.execute_command_internal()
                self.terminal.current_cmd = ""

        finally:
            # 恢复脚本执行状态
            self.terminal.is_script_execution = False
            print("脚本解析执行完成")

    def _execute_function(self, func_info, context):
        """在独立上下文中执行函数体"""
        # 创建新的解析器实例
        nested_parser = ShellParser(self.terminal)
        # 设置变量为全局变量和局部变量的组合
        nested_parser.variables = {**context['variables'], **context['local_vars']}

        for line in func_info['lines']:
            stripped_line = line.strip()
            print(f"执行函数内语句: {stripped_line}")

            # 处理local语句（保持原有逻辑不变）
            if stripped_line.startswith('local '):
                parts = stripped_line[6:].strip().split('=', 1)
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    var_value = parts[1].strip()

                    # 处理算术扩展和变量替换
                    var_value = nested_parser._substitute_arithmetic(var_value)
                    var_value = nested_parser._substitute_variables(var_value)

                    # 存储到局部变量
                    context['local_vars'][var_name] = var_value
                    nested_parser.variables[var_name] = var_value  # 更新当前解析器的变量
                    print(f"局部变量 {var_name} 赋值为: {var_value}")
                continue

            # 处理return语句（保持原有逻辑不变）
            if stripped_line.startswith('return '):
                return_value = stripped_line[7:].strip()

                # 处理算术扩展和变量替换
                return_value = nested_parser._substitute_arithmetic(return_value)
                return_value = nested_parser._substitute_variables(return_value)

                print(f"函数返回: {return_value}")
                return return_value  # 直接返回，终止函数执行

            # 执行其他类型的语句
            nested_parser.parse(line, self.context_dir)

        return context.get('return_value')

    def _substitute_variables(self, value):
        """处理变量替换（保持原有逻辑不变）"""
        def replace_var(match):
            cmd_sub = match.group(1)
            var_braced = match.group(2)
            var_simple = match.group(3)

            if cmd_sub:
                # 执行命令
                self.parse(cmd_sub, self.context_dir)
            elif var_braced:
                var_value = self.variables.get(var_braced, '')
                print(f"变量替换: ${var_braced} 替换为: {var_value}")
                return var_value
            elif var_simple:
                var_value = self.variables.get(var_simple, '')
                print(f"变量替换: ${var_simple} 替换为: {var_value}")
                return var_value
            return ''

        result = self.command_sub_re.sub(replace_var, value)
        print(f"变量替换后结果: {result}")
        return result

    def _substitute_commands(self, value):
        """替换命令替换 $(command)（保持原有逻辑不变）"""
        pattern = re.compile(r'\$\((.*?)\)')
        result = pattern.sub(lambda m: self._execute_command(m.group(1)), value)
        print(f"命令替换后结果: {result}")
        return result

    def _execute_command(self, cmd):
        """执行命令并返回结果（保持原有逻辑不变）"""
        original_cmd = self.terminal.current_cmd
        self.terminal.current_cmd = cmd
        print(f"执行子命令: {cmd}")

        self.terminal.execute_command_internal()

        self.terminal.current_cmd = original_cmd
        return ""

    def _evaluate_condition(self, condition):
        """评估条件表达式（保持原有逻辑不变）"""
        # 移除多余的分号
        condition = condition.rstrip(';')
        condition = self._substitute_variables(condition)
        tokens = shlex.split(condition)
        if len(tokens) >= 3 and tokens[0] == '[' and tokens[-1] == ']':
            inner_condition = " ".join(tokens[1:-1])
            parts = inner_condition.split()
            if len(parts) == 3:
                left = parts[0]
                op = parts[1]
                right = parts[2]

                try:
                    left_num = int(left)
                    right_num = int(right)
                    if op == '-gt':
                        return left_num > right_num
                    elif op == '-lt':
                        return left_num < right_num
                    elif op == '-ge':
                        return left_num >= right_num
                    elif op == '-le':
                        return left_num <= right_num
                    elif op == '-eq':
                        return left_num == right_num
                    elif op == '-ne':
                        return left_num != right_num
                except ValueError:
                    pass

        return False

    def _substitute_arithmetic(self, value):
        """处理算术扩展（保持原有逻辑不变）"""

        def replace_arithmetic(match):
            expr = match.group(1)
            expr = self._substitute_variables(expr)
            try:
                for var, val in self.variables.items():
                    try:
                        num_val = int(val)
                        expr = expr.replace(var, str(num_val))
                    except ValueError:
                        pass
                result = eval(expr)
                print(f"算术扩展: $(( {expr} )) 结果为: {result}")
                return str(result)
            except:
                print(f"算术扩展失败: $(( {expr} ))")
                return match.group(0)

        result = self.arithmetic_re.sub(replace_arithmetic, value)
        print(f"算术扩展后结果: {result}")
        return result