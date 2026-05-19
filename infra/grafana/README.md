# Grafana

Grafana is started by Docker Compose and provisioned with:

- `infra/grafana/provisioning/datasources/prometheus.yml`
- `infra/grafana/provisioning/dashboards/taurus.yml`
- `infra/grafana/dashboards/taurus-system.json`
- `infra/grafana/dashboards/taurus-trading.json`

Local Grafana runs at `http://localhost:3000` with `admin` / `admin`.
