from __future__ import annotations

import time

import pytest

from mxg_n5183b import MXGCommandError, MXGError, MXGParameterError, N5183B


class TestConnection:
    def test_get_idn(self, sg):
        assert "N5183B" in sg.get_idn()

    def test_context_manager_turns_off_output_on_exit(
        self, fake_instrument, mocker=None
    ):
        from unittest.mock import MagicMock, patch

        with patch("mxg_n5183b.driver.pyvisa.ResourceManager") as mock_rm_cls:
            mock_rm = MagicMock()
            mock_rm.open_resource.return_value = fake_instrument
            mock_rm_cls.return_value = mock_rm

            with N5183B("TCPIP::192.0.2.1::INSTR") as sg_ctx:
                sg_ctx.set_rf_output(True)
            assert fake_instrument._output_state == "0"

    def test_empty_resource_name_rejected(self):
        with pytest.raises(MXGParameterError):
            N5183B("")


class TestFrequency:
    def test_set_and_get_frequency(self, sg):
        sg.set_frequency(2.5e9)
        assert sg.get_frequency() == pytest.approx(2.5e9)

    def test_frequency_out_of_range_rejected(self, sg):
        with pytest.raises(MXGParameterError):
            sg.set_frequency(30e9)
        with pytest.raises(MXGParameterError):
            sg.set_frequency(1)

    def test_step_frequency_up(self, sg):
        sg.set_frequency(1e9)
        new_freq = sg.step_frequency(1e8, direction="up")
        assert new_freq == pytest.approx(1.1e9)

    def test_step_frequency_down(self, sg):
        sg.set_frequency(1e9)
        new_freq = sg.step_frequency(1e8, direction="down")
        assert new_freq == pytest.approx(0.9e9)

    def test_step_frequency_invalid_direction(self, sg):
        with pytest.raises(MXGParameterError):
            sg.step_frequency(1e8, direction="sideways")


class TestPower:
    def test_set_and_get_power(self, sg):
        sg.set_power(-5.0)
        assert sg.get_power() == pytest.approx(-5.0)


class TestOutputAndModulation:
    def test_rf_output_toggle(self, sg):
        sg.set_rf_output(True)
        assert sg.get_rf_output_state() is True
        sg.set_rf_output(False)
        assert sg.get_rf_output_state() is False

    def test_modulation_toggle(self, sg):
        sg.enable_modulation(True)
        assert sg.get_modulation_state() is True


class TestErrorChecking:
    def test_command_error_raised_and_drains_queue(self, sg, fake_instrument):
        fake_instrument.error_queue.append((-222, "Data out of range"))
        with pytest.raises(MXGCommandError) as excinfo:
            sg.set_power(999)
        assert excinfo.value.code == -222

    def test_no_error_does_not_raise(self, sg):
        # Default FakeInstrument queue is empty -> "No error" every time.
        sg.set_power(0)  # should not raise


class TestSoftwareSweep:
    def test_sweep_runs_and_stops(self, sg):
        visited = []
        sg.start_software_sweep(
            start_hz=1e9,
            stop_hz=1.2e9,
            step_hz=1e8,
            dwell_s=0.01,
            callback=visited.append,
        )
        # Give the background thread a moment to make progress.
        time.sleep(0.2)
        sg.stop_software_sweep()
        assert not sg.is_software_sweeping
        assert len(visited) > 0

    def test_sweep_rejects_bad_range(self, sg):
        with pytest.raises(MXGParameterError):
            sg.start_software_sweep(start_hz=1e9, stop_hz=1.05e9, step_hz=1e8)

    def test_cannot_start_two_sweeps_at_once(self, sg):
        sg.start_software_sweep(start_hz=1e9, stop_hz=2e9, step_hz=1e8, dwell_s=1.0)
        with pytest.raises(MXGError):
            sg.start_software_sweep(start_hz=1e9, stop_hz=2e9, step_hz=1e8, dwell_s=1.0)
        sg.stop_software_sweep()


class TestHardwareSweep:
    def test_configure_step_sweep_sends_expected_commands(self, sg, fake_instrument):
        sg.configure_step_sweep(start_hz=1e9, stop_hz=2e9, points=51, dwell_s=0.01)
        joined = " ".join(fake_instrument.written_commands)
        assert ":LIST:TYPE STEP" in joined
        assert ":FREQ:STAR 1000000000.0" in joined
        assert ":FREQ:STOP 2000000000.0" in joined
        assert ":SWE:POIN 51" in joined

    def test_configure_step_sweep_rejects_bad_points(self, sg):
        with pytest.raises(MXGParameterError):
            sg.configure_step_sweep(start_hz=1e9, stop_hz=2e9, points=1)

    def test_start_and_stop_hardware_sweep(self, sg, fake_instrument):
        sg.configure_step_sweep(start_hz=1e9, stop_hz=2e9, points=11, dwell_s=0.01)
        sg.start_hardware_sweep(trigger_source="imm", continuous=True)
        assert ":FREQ:MODE LIST" in fake_instrument.written_commands
        sg.stop_hardware_sweep()
        assert ":ABOR" in fake_instrument.written_commands
        assert fake_instrument.written_commands[-1] in (":FREQ:MODE CW",)

    def test_invalid_trigger_source_rejected(self, sg):
        with pytest.raises(MXGParameterError):
            sg.start_hardware_sweep(trigger_source="banana")


class TestShellDispatch:
    """Tests the shell's command parsing (_run_shell_command), not the
    input()/print() loop itself."""

    def test_freq_command(self, sg, capsys):
        from mxg_n5183b.cli import _run_shell_command

        _run_shell_command(sg, "freq 1.5e9")
        _run_shell_command(sg, "freq?")
        captured = capsys.readouterr()
        assert "1.5e+09" in captured.out or "1500000000" in captured.out

    def test_power_command(self, sg, capsys):
        from mxg_n5183b.cli import _run_shell_command

        _run_shell_command(sg, "power -7.5")
        _run_shell_command(sg, "power?")
        captured = capsys.readouterr()
        assert "-7.50 dBm" in captured.out

    def test_output_command(self, sg, capsys):
        from mxg_n5183b.cli import _run_shell_command

        _run_shell_command(sg, "output on")
        _run_shell_command(sg, "output?")
        captured = capsys.readouterr()
        assert "ON" in captured.out

    def test_unknown_command(self, sg, capsys):
        from mxg_n5183b.cli import _run_shell_command

        _run_shell_command(sg, "banana")
        captured = capsys.readouterr()
        assert "Unknown command" in captured.out

    def test_invalid_argument_raises_value_error(self, sg):
        from mxg_n5183b.cli import _run_shell_command

        with pytest.raises(ValueError):
            _run_shell_command(sg, "freq not-a-number")


class TestConvenience:
    def test_set_power_then_sweep(self, sg, fake_instrument):
        sg.set_power_then_sweep(
            power_dbm=-3.0, start_hz=1e9, stop_hz=1.2e9, step_hz=1e8, dwell_s=0.01
        )
        time.sleep(0.2)
        sg.stop_software_sweep()
        assert fake_instrument._power == pytest.approx(-3.0)
        assert fake_instrument._output_state == "1"
