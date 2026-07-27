"""PydanticOutputParser 单元测试。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from app.llm_gateway.output_parser import OutputParseError, PydanticOutputParser


class TestModel(BaseModel):
    """测试用 Pydantic 模型。"""

    name: str = Field(description="名称")
    age: int = Field(description="年龄")
    active: bool = Field(default=False, description="是否激活")


class TestOutputParser:
    """PydanticOutputParser 测试。"""

    def setup_method(self):
        self.parser = PydanticOutputParser(TestModel)

    def test_get_response_format(self):
        """测试 response_format 生成。"""
        fmt = self.parser.get_response_format()
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["name"] == "TestModel"

    def test_get_format_instruction(self):
        """测试格式指令生成。"""
        instr = self.parser.get_format_instruction()
        assert "TestModel" in instr
        assert "name" in instr
        assert "age" in instr

    def test_parse_direct_json(self):
        """测试直接 JSON 解析。"""
        result = self.parser.parse('{"name": "Alice", "age": 30}')
        assert isinstance(result, TestModel)
        assert result.name == "Alice"
        assert result.age == 30

    def test_parse_from_code_block(self):
        """测试从代码块解析。"""
        text = '一些文字\n```json\n{"name": "Bob", "age": 25}\n```\n更多文字'
        result = self.parser.parse(text)
        assert result.name == "Bob"
        assert result.age == 25

    def test_parse_from_code_block_no_label(self):
        """测试从无标签代码块解析。"""
        text = '```\n{"name": "Charlie", "age": 35}\n```'
        result = self.parser.parse(text)
        assert result.name == "Charlie"
        assert result.age == 35

    def test_parse_from_braces(self):
        """测试从花括号提取。"""
        text = '返回结果是 {"name": "Dave", "age": 40} 请查收'
        result = self.parser.parse(text)
        assert result.name == "Dave"
        assert result.age == 40

    def test_parse_with_defaults(self):
        """测试带默认值的解析。"""
        result = self.parser.parse('{"name": "Eve", "age": 28}')
        assert result.active is False

    def test_parse_failure_raises_error(self):
        """测试解析失败抛出异常。"""
        with pytest.raises(OutputParseError):
            self.parser.parse("这不是 JSON")

    def test_parse_invalid_type_raises_error(self):
        """测试类型不匹配时抛出异常。"""
        with pytest.raises(OutputParseError):
            self.parser.parse('{"name": "Frank", "age": "not_a_number"}')

    def test_direct_json_with_extra_fields(self):
        """测试多余的字段被忽略。"""
        result = self.parser.parse('{"name": "Grace", "age": 22, "extra": "ignored"}')
        assert result.name == "Grace"
        assert result.age == 22
