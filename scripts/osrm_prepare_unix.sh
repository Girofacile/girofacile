#!/usr/bin/env bash
# Usage: bash scripts/osrm_prepare_unix.sh <local.osm.pbf|https://...osm.pbf> [basename]
# Optional OSRM_DATA_DIR, OSRM_IMAGE; no implicit downloads, no server startup.
set -euo pipefail
[[ $# -ge 1 && $# -le 2 ]] || { echo "Usage: $0 <file.osm.pbf|URL> [basename]" >&2; exit 2; }
source_pbf=$1
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
data_dir=${OSRM_DATA_DIR:-"$root/data/osrm"}
image=${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend@sha256:8a1b1bc938412f15f9b5b32d794c4ec6bf4a85dfbbabfa0a014b70b187edb53b}
filename=${source_pbf%%\?*}
filename=${filename##*/}
[[ "$filename" == *.osm.pbf ]] || { echo 'Source must end in .osm.pbf' >&2; exit 2; }
dataset=${2:-${filename%.osm.pbf}}
[[ "$dataset" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]] || { echo 'Invalid dataset basename' >&2; exit 2; }
command -v docker >/dev/null
docker info >/dev/null
mkdir -p "$data_dir"
data_dir=$(cd "$data_dir" && pwd)
if compgen -G "$data_dir/$dataset.osrm*" >/dev/null; then
    echo 'Dataset already exists. Choose a new basename; never overwrite a running dataset.' >&2
    exit 2
fi
pbf="$data_dir/$dataset.osm.pbf"
case "$source_pbf" in
    http://*|https://*)
        [[ ! -e "$pbf" && ! -e "$pbf.part" ]] || { echo 'Download destination already exists' >&2; exit 2; }
        # A failed partial download remains identifiable and is never preprocessed.
        curl --fail --location --proto '=http,https' --proto-redir '=http,https' --output "$pbf.part" "$source_pbf"
        mv "$pbf.part" "$pbf"
        ;;
    *)
        [[ -f "$source_pbf" ]] || { echo 'PBF file not found' >&2; exit 2; }
        original=$(cd "$(dirname "$source_pbf")" && pwd)/$(basename "$source_pbf")
        if [[ "$original" != "$pbf" ]]; then
            [[ ! -e "$pbf" ]] || { echo 'PBF destination already exists' >&2; exit 2; }
            cp "$source_pbf" "$pbf"
        fi
        ;;
esac
[[ -s "$pbf" ]] || { echo 'Empty PBF' >&2; exit 2; }
docker run --rm --user "$(id -u):$(id -g)" --volume "$data_dir:/data" "$image" osrm-extract -p /opt/car.lua "/data/$dataset.osm.pbf"
docker run --rm --user "$(id -u):$(id -g)" --volume "$data_dir:/data" "$image" osrm-partition "/data/$dataset.osrm"
docker run --rm --user "$(id -u):$(id -g)" --volume "$data_dir:/data" "$image" osrm-customize "/data/$dataset.osrm"
# .osrm is a basename, not necessarily a real file in modern OSRM releases.
for suffix in partition cells cell_metrics mldgr nbg_nodes ebg_nodes edges geometry names properties ramIndex fileIndex; do
    [[ -s "$data_dir/$dataset.osrm.$suffix" ]] || { echo "Missing output: $dataset.osrm.$suffix" >&2; exit 1; }
done
# Ask the same serving binary to load every required sidecar and then exit.
docker run --rm --user "$(id -u):$(id -g)" --volume "$data_dir:/data:ro" "$image" osrm-routed --algorithm mld --trial=1 "/data/$dataset.osrm"
printf 'Dataset ready: %s\nSet OSRM_DATASET_BASENAME=%s and change OSRM_CACHE_VERSION before restarting OSRM.\n' "$pbf" "$dataset"
