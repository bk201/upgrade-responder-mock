# Upgrade mock

A mock upgrade-responder and `version.yaml` download site that runs inside the test cluster, for testing upgrade paths between Community and Prime releases without published releases. The ISOs stay wherever you host them; the mock only points to them.

- `POST <any path>`: the upgrade check. Answers with the releases in `releases.json` that are offered, and logs the request, including the `serverFlavor` the cluster reports.
- `GET /<id>/version.yaml` (or `version-arm64.yaml`): a `version.yaml` generated from the release, labeled with its flavor and pointing to its ISO. It has a fake `isoChecksum`, because the version syncer skips Versions without one.
- `GET /<id>/version.yaml?import`: the same without `isoChecksum`, for importing a Version to upgrade with. The upgrade then downloads the ISO without verifying it.

## Files

- `server.py`: the server (Python standard library only).
- `releases.json`: the releases. Each entry has:
  - the responder fields: `name`, `releaseDate`, `minUpgradableVersion`, `tags`;
  - `flavor`: the `harvesterhci.io/serverFlavor` label; omit it for an unlabeled Version;
  - `isoURL`: where the cluster downloads the ISO. If omitted, a fake URL is used, which is enough for the version syncer but not for an upgrade;
  - `id`: URL path and Version name, defaults to `name`, so two flavors of the same version can coexist;
  - `offer`: `false` keeps the release out of the upgrade check, so it can only be imported.
- `upgrade-mock.yaml`: namespace, the Deployment, and a NodePort Service on port 30880. The Deployment runs `server.py` and `releases.json` from the `upgrade-mock` ConfigMap, created from those two files.

The default `releases.json` matches the PR test plan:

| id | Flavor | Offered | ISO |
|----|--------|---------|-----|
| `v1.99.0` | prime | yes, tagged `prime` | Prime v1.99.0 |
| `v1.99.1` | community | yes, tagged `community` | none needed (syncer tests only) |
| `v1.99.0-community` | community | no, import only | Community v1.99.0 |

## Deploy

Host the ISOs on any HTTP server the cluster can reach, and fill in `isoURL` in `releases.json`. Then:

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

Import a release as a user would, from any machine that reaches a node:

```sh
curl -s 'http://<node IP>:30880/v1.99.0/version.yaml?import' | kubectl create -f -
```

Trigger a version sync by restarting Harvester, then check the request and the Versions:

```sh
kubectl -n harvester-system rollout restart deploy/harvester
kubectl -n upgrade-mock logs deploy/upgrade-mock | grep 'upgrade check'
kubectl -n harvester-system get versions.harvesterhci.io --show-labels
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
