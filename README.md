# Upgrade mock

A mock upgrade-responder and `version.yaml` download site that runs inside the test cluster, for testing upgrade paths between Community and Prime releases without published releases.

- `POST <any path>`: the upgrade check. Answers with the releases in `releases.json`, and logs the request, including the `serverFlavor` the cluster reports.
- `GET /<name>/version.yaml` (or `version-arm64.yaml`): a `version.yaml` generated from the release, labeled with its flavor. It points to a fake ISO with a fake checksum: enough for the version syncer, which skips Versions without them, but not for an upgrade.

Versions to upgrade with are imported from `versions/`, as a user would import a `version.yaml`. They point to ISOs you host on any HTTP server the cluster can reach.

## Files

- `server.py`: the server (Python standard library only).
- `sync-versions.sh`: triggers a version sync and waits for it.
- `releases.json`: the releases. Each entry has the responder fields (`name`, `releaseDate`, `minUpgradableVersion`, `tags`) and `flavor`, the `harvesterhci.io/serverFlavor` label; omit it for an unlabeled Version.
- `versions/`: Versions to import.
  - `prime-v1.99.0.yaml`: Prime v1.99.0, to switch a Community cluster. Set `isoURL` to the Prime ISO.
  - `community-v1.99.0.yaml`: Community v1.99.0, which a Prime cluster must not upgrade to. The upgrade webhook rejects it before the ISO is downloaded, so its `isoURL` doesn't matter.
  - `legacy-v1.99.1.yaml`: Community v1.99.1 as a syncer from before the `versionSource` label created it, with no labels and the release date from `releases.json`. A sync should adopt it by labeling it `versionSource=upgrade-checker`; with another `releaseDate`, it stays unlabeled as a user-created Version. Delete any synced `v1.99.1` before creating it.
- `upgrade-mock.yaml`: namespace, the Deployment, and a NodePort Service on port 30880. The Deployment runs `server.py` and `releases.json` from the `upgrade-mock` ConfigMap, created from those two files.

The default `releases.json` offers Prime `v1.99.0` (tagged `prime`) and Community `v1.99.1` (tagged `community`).

The imported Versions have no `isoChecksum`, so the upgrade downloads the ISO without verifying it. Add `isoChecksum` (`sha512sum <iso>`) to verify it.

## Deploy

```sh
kubectl apply -f upgrade-mock.yaml
kubectl -n upgrade-mock create configmap upgrade-mock --from-file=server.py --from-file=releases.json
kubectl -n upgrade-mock rollout status deploy/upgrade-mock
```

Point Harvester at the mock:

```sh
kubectl patch settings.harvesterhci.io upgrade-checker-url --type merge \
  -p '{"value":"http://upgrade-mock.upgrade-mock.svc.cluster.local:8000/v1/checkupgrade"}'
kubectl patch settings.harvesterhci.io release-download-url --type merge \
  -p '{"value":"http://upgrade-mock.upgrade-mock.svc.cluster.local:8000"}'
kubectl patch settings.harvesterhci.io upgrade-checker-enabled --type merge -p '{"value":"true"}'
```

The version syncer does nothing while `upgrade-checker-enabled` is `false`.

## Use

Import a Version:

```sh
kubectl create -f versions/prime-v1.99.0.yaml
```

Trigger a version sync with `./sync-versions.sh`. It restarts Harvester, waits for the upgrade check from the new pods to reach the mock (up to `TIMEOUT` seconds, default 300), then prints the request, including the reported `serverFlavor`, and the Versions. Each command is printed before it runs.

```sh
./sync-versions.sh
```

To change the releases, edit `releases.json` and update the ConfigMap. The server reads `releases.json` on every request, so the change applies once kubelet syncs the mounted file, usually within a minute. After changing `server.py`, also restart the Deployment.

```sh
kubectl -n upgrade-mock create configmap upgrade-mock --from-file=server.py --from-file=releases.json \
  --dry-run=client -o yaml | kubectl replace -f -
kubectl -n upgrade-mock rollout restart deploy/upgrade-mock   # only after changing server.py
```

## Clean up

```sh
kubectl patch settings.harvesterhci.io upgrade-checker-url --type merge -p '{"value":""}'
kubectl patch settings.harvesterhci.io release-download-url --type merge -p '{"value":""}'
kubectl patch settings.harvesterhci.io upgrade-checker-enabled --type merge -p '{"value":""}'
kubectl delete namespace upgrade-mock
```

An empty value makes these settings fall back to their defaults.
