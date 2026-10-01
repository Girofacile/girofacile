"""Exercise preparation scripts with fake Docker; no image/dataset downloads."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = 'partition cells cell_metrics mldgr nbg_nodes ebg_nodes edges geometry names properties ramIndex fileIndex'
BASH = shutil.which('bash') if os.name != 'nt' else str(Path('C:/Program Files/Git/bin/bash.exe'))
PWSH = shutil.which('pwsh')


def run_script(tmp_path, kind, source='sud-latest.osm.pbf', fail='', missing='', basename=None):
    target = tmp_path / 'output with spaces'
    target.mkdir(exist_ok=True)
    source_path = tmp_path / source if not source.startswith('https://') else source
    if isinstance(source_path, Path):
        source_path.write_bytes(b'fake-pbf-preserved')
    log = tmp_path / 'calls.log'
    dataset = basename or source.rsplit('/', 1)[-1].removesuffix('.osm.pbf')
    env = dict(os.environ, FAKE_DATA=str(target), FAKE_BASE=dataset, FAKE_LOG=str(log),
               FAKE_FAIL=fail, FAKE_MISSING=missing, OSRM_DATA_DIR=str(target))
    if kind == 'powershell':
        if not PWSH:
            pytest.skip('PowerShell not installed')
        wrapper = tmp_path / 'fake.ps1'
        wrapper.write_text('''function docker {
    $stage = @($args | Where-Object { $_ -like 'osrm-*' })
    $name = if ($stage.Count) { $stage[0] } else { 'info' }
    Add-Content -LiteralPath $env:FAKE_LOG -Value $name
    $global:LASTEXITCODE = 0
    if ($name -eq $env:FAKE_FAIL) { $global:LASTEXITCODE = 17; return }
    if ($name -eq 'osrm-customize') {
        foreach ($suffix in 'SUFFIXES'.Split(' ')) {
            if ($suffix -ne $env:FAKE_MISSING) { Set-Content -LiteralPath (Join-Path $env:FAKE_DATA "$env:FAKE_BASE.osrm.$suffix") -Value 'data' }
        }
    }
}
function Invoke-WebRequest { param($Uri,$OutFile,[switch]$UseBasicParsing)
    Add-Content -LiteralPath $env:FAKE_LOG -Value 'download'
    Set-Content -LiteralPath $OutFile -Value 'downloaded-pbf'
}
& $args[0] -Source $args[1] -DataDirectory $env:FAKE_DATA -Basename $env:FAKE_BASE
'''.replace('SUFFIXES', SUFFIXES))
        command = [PWSH, '-NoProfile', '-File', str(wrapper), str(ROOT/'scripts/osrm_prepare_windows.ps1'), str(source_path)]
    else:
        if not BASH or not Path(BASH).exists():
            pytest.skip('Bash not installed')
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir(exist_ok=True)
        docker = bin_dir / 'docker'
        docker.write_text('''#!/usr/bin/env bash
set -eu
stage=info
for arg in "$@"; do case "$arg" in osrm-*) stage=$arg;; esac; done
echo "$stage" >> "$FAKE_LOG"
[[ "$stage" != "$FAKE_FAIL" ]] || exit 17
if [[ "$stage" == osrm-customize ]]; then
 for suffix in SUFFIXES; do
  [[ "$suffix" == "$FAKE_MISSING" ]] || printf data > "$FAKE_DATA/$FAKE_BASE.osrm.$suffix"
 done
fi
'''.replace('SUFFIXES', SUFFIXES), newline='\n')
        docker.chmod(0o755)
        curl = bin_dir / 'curl'
        curl.write_text('''#!/usr/bin/env bash
set -eu
echo download >> "$FAKE_LOG"
while [[ "$1" != --output ]]; do shift; done
printf downloaded-pbf > "$2"
''', newline='\n')
        curl.chmod(0o755)
        env['FAKE_BIN'] = str(bin_dir)
        # Git Bash prepends its own bin directory on Windows. Put the fakes
        # first inside Bash as well, so curl can never contact the network.
        command = [BASH, '-c', 'if command -v cygpath >/dev/null; then FAKE_BIN=$(cygpath -u "$FAKE_BIN"); fi; export PATH="$FAKE_BIN:$PATH"; exec bash "$@"',
                   'prepare-test', str(ROOT/'scripts/osrm_prepare_unix.sh'), str(source_path), dataset]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    calls = log.read_text().splitlines() if log.exists() else []
    return result, calls, target, source_path


@pytest.mark.parametrize('kind', ['bash', 'powershell'])
@pytest.mark.parametrize('source', ['sud-latest.osm.pbf', 'italy-latest.osm.pbf', 'future-region.osm.pbf', 'https://example.test/region.osm.pbf'])
def test_prepare_sequence_and_preserved_pbf(tmp_path, kind, source):
    result, calls, target, original = run_script(tmp_path, kind, source)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls == ['info'] + (['download'] if source.startswith('https:') else []) + ['osrm-extract', 'osrm-partition', 'osrm-customize', 'osrm-routed']
    if isinstance(original, Path):
        assert original.read_bytes() == b'fake-pbf-preserved'
    assert len(list(target.glob('*.osm.pbf'))) == 1


@pytest.mark.parametrize('kind', ['bash', 'powershell'])
@pytest.mark.parametrize('stage', ['osrm-extract', 'osrm-partition', 'osrm-customize', 'osrm-routed'])
def test_stops_immediately_on_docker_failure(tmp_path, kind, stage):
    result, calls, _, _ = run_script(tmp_path, kind, fail=stage)
    assert result.returncode != 0
    assert calls[-1] == stage
    assert calls == ['info', 'osrm-extract', 'osrm-partition', 'osrm-customize', 'osrm-routed'][:calls.index(stage)+1]


@pytest.mark.parametrize('kind', ['bash', 'powershell'])
def test_missing_mld_file_is_failure(tmp_path, kind):
    result, _, _, _ = run_script(tmp_path, kind, missing='mldgr')
    assert result.returncode != 0
    assert 'mldgr' in result.stdout + result.stderr


@pytest.mark.parametrize('kind', ['bash', 'powershell'])
def test_existing_dataset_is_not_overwritten(tmp_path, kind):
    target = tmp_path / 'output with spaces'
    target.mkdir()
    existing = target / 'sud-latest.osrm.partition'
    existing.write_text('preserved')
    result, calls, _, _ = run_script(tmp_path, kind)
    assert result.returncode != 0 and calls == ['info']
    assert existing.read_text() == 'preserved'


@pytest.mark.parametrize('kind', ['bash', 'powershell'])
def test_basename_cannot_escape_data_directory(tmp_path, kind):
    result, calls, _, _ = run_script(tmp_path, kind, basename='../outside')
    assert result.returncode != 0 and not calls
