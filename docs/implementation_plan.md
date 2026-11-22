# Whole-room wall RMS implementation plan

Goal: 输入整个房间，自动发现墙面，按编号/可选四点计算 RMS，建立独立可复现 Git 项目。

Architecture: geometry discovery plus optional external semantic labels; full-resolution measurement with separately recorded RANSAC support and restored surface sets. Reuse frozen old IO/geometry source. Python NumPy/SciPy/Matplotlib, no trained network claimed.

- [x] Tests: create synthetic rooms and expected walls; test `discover(points_m, config, labels=None)`, `measure_wall(points_m, wall, roi=None, mode='expanded')`, CLI persistence/selection and rejection. Run unittest and observe missing functionality before implementation.
- [x] IO/config: vendor existing modules with hashes; validate finite positive thresholds, explicit m/mm and up direction; read indexed NPY semantic arrays; preserve original point IDs.
- [x] Geometry: voxel representatives; reproducible iterative RANSAC; cKDTree DBSCAN/largest component; SVD; ground selection; geometric wall checks; deterministic IDs and dominant flags; restore original points using projected support footprint and slab.
- [x] Measurement: refit chosen points, report RMS/P95/max/coverage and paper-inlier comparison; optional four-point ROI intersection; never residual-trim final set.
- [x] CLI/artifacts: discover/measure/run, immutable nonempty output handling, JSON/CSV/NPZ hashes, catalog/preview, per-wall distance plots, self-contained offline HTML selecting wall IDs; schema checks and no absolute portable defaults.
- [x] Verify synthetic fixture, degenerate/no-wall data, labels, units/rotation, recovery of bulge, CLI selected/all and stale/corrupt catalog. Independent eigenvalue computation on saved point sets.
- [x] Run M04 and M26 from provided ZIP, inspect top views/elevations, record measured wall counts, RMS and runtime with settings. Sensitivity compare paper and expanded, no GT-driven tuning.
- [x] Write Chinese quickstart, interface/algorithm explanations, experiment report and limitations; record reused source. Initialize Git main, check exclusions and secret patterns, commit, verify clean status and reproducible CLI from fresh checkout.
