from click.testing import CliRunner
from eemeter import cli

def test_cli_sample():
	runner = CliRunner()
	result = runner.invoke(cli.sample, obj={})
	assert result.exit_code == 0

def test_cli_analyze_returns_meter_output_with_derivatives():
        retval = cli._analyze('eemeter/sample_data', None, None)
        series = [i['series'] for i in retval[0]['derivatives']]
        assert "Baseline model, reporting period" in series