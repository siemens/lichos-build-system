"""
Base test classes and utilities for lichoscli tests
"""

import unittest
import argparse
from unittest.mock import Mock
from lichoscli.commands.base import Command, CommandRegister, CommandExecutor
from tests import fixtures


class TestCommandRegister(unittest.TestCase):
    def setUp(self):
        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

        class TestCmd(Command):
            def execute(self) -> int:
                return 0

            @staticmethod
            def register_parser(subparsers):
                parser = subparsers.add_parser("test")
                parser.add_argument("--test-arg")

        CommandRegister._commands["test"] = TestCmd
        self.TestCmd = TestCmd

    def test_register_command(self):
        self.assertIn("test", CommandRegister._commands)
        self.assertEqual(CommandRegister._commands["test"], self.TestCmd)

    def test_get_command(self):
        command_class = CommandRegister.get_command("test")
        self.assertEqual(command_class, self.TestCmd)
        self.assertIsNone(CommandRegister.get_command("non-existent"))

    def _disabled_test_register_parser(self):
        mock_subparsers = Mock(spec=argparse._SubParsersAction)
        CommandRegister.register_all_parsers(mock_subparsers)
        mock_subparsers.add_parser.assert_called_once_with("test")


class TestCommandExecutor(unittest.TestCase):
    def setUp(self):
        self.pkg_handler = fixtures.create_mock_pkg_handler()
        self.args = fixtures.create_mock_args()
        self.executor = CommandExecutor(self.pkg_handler, self.args)

        CommandRegister._commands = {}
        CommandRegister._parser_hooks = {}

    def test_execute_valid_command(self):
        """Test executing a valid command"""
        mock_execute = Mock()

        class TestExecuteCmd(Command):
            def execute(self):
                mock_execute()

        CommandRegister._commands["test-execute"] = TestExecuteCmd

        command_args = Mock()
        command_args.command = "test-execute"

        self.executor.execute(command_args)
        mock_execute.assert_called_once()

    def test_execute_invalid_command(self):
        """Test executing an invalid command"""
        command_args = Mock()
        command_args.command = "non-existent"

        with self.assertRaises(ValueError) as context:
            self.executor.execute(command_args)

        self.assertIn("Unknown command", str(context.exception))

    def test_execute_no_command(self):
        """Test executing with no command specified"""
        with self.assertRaises(ValueError) as context:
            self.executor.execute(None)

        self.assertEqual(str(context.exception), "No command specified")

    def test_command_with_arguments(self):
        """Test executing a command with arguments"""
        test_value = []

        class TestArgsCommand(Command):
            def execute(self):
                test_value.append("test-value")
                return 0

        CommandRegister._commands["test-args"] = TestArgsCommand

        command_args = Mock()
        command_args.command = "test-args"
        command_args.test_param = "test-value"

        self.executor = CommandExecutor(self.pkg_handler, command_args)
        self.executor.execute(command_args)

        self.assertEqual(len(test_value), 1)
        self.assertEqual(test_value[0], "test-value")
