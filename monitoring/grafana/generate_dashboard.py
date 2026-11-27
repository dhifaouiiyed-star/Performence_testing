"""Generates the two Grafana dashboards (one per architecture / compose profile):
    dashboards/monolith.json        -> "Monolith"
    dashboards/microservices.json   -> "Microservices"
Run:  python monitoring/grafana/generate_dashboard.py
"""
import json
import pathlib

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
OUT = pathlib.Path(__file__).parent / "dashboards"


class Dashboard:
    def __init__(self):
        self.panels, self._id, self._y, self._x, self._h = [], 0, 0, 0, 0

    def _pos(self, w, h):
        if self._x + w > 24:
            self._y += self._h
            self._x, self._h = 0, 0
        pos = {"h": h, "w": w, "x": self._x, "y": self._y}
        self._x += w
        self._h = max(self._h, h)
        return pos

    def _next_id(self):
        self._id += 1
        return self._id

    def row(self, title):
        if self._x:
            self._y += self._h
            self._x, self._h = 0, 0
        self.panels.append({"type": "row", "id": self._next_id(), "title": title, "collapsed": False,
                            "gridPos": {"h": 1, "w": 24, "x": 0, "y": self._y}, "panels": []})
        self._y += 1

    def stat(self, title, expr, unit="short", w=3, decimals=None, thresholds=None, desc="", instant=False):
        steps = thresholds or [{"color": "green", "value": None}]
        defaults = {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}}
        if decimals is not None:
            defaults["decimals"] = decimals
        self.panels.append({
            "type": "stat", "id": self._next_id(), "title": title, "description": desc, "datasource": PROM,
            "gridPos": self._pos(w, 4),
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": "background", "graphMode": "none" if instant else "area", "textMode": "value"},
            "targets": [{"datasource": PROM, "refId": "A", "expr": expr, "instant": instant, "range": not instant}],
        })

    def ts(self, title, targets, unit="short", w=12, h=8, ds=PROM, desc="", stack=False):
        custom = {"lineWidth": 2, "fillOpacity": 10}
        if stack:
            custom["stacking"] = {"mode": "normal", "group": "A"}
        self.panels.append({
            "type": "timeseries", "id": self._next_id(), "title": title, "description": desc, "datasource": ds,
            "gridPos": self._pos(w, h),
            "fieldConfig": {"defaults": {"unit": unit, "custom": custom}, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "lastNotNull"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}},
            "targets": [dict(datasource=ds, refId=chr(65 + i), **t) for i, t in enumerate(targets)],
        })

    def logs(self, title, expr, h=12):
        self.panels.append({
            "type": "logs", "id": self._next_id(), "title": title, "datasource": LOKI, "gridPos": self._pos(24, h),
            "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": True},
            "targets": [{"datasource": LOKI, "refId": "A", "expr": expr}],
        })


def q(expr, legend=""):
    return {"expr": expr, "legendFormat": legend}


def build(arch):
    """arch: 'monolith' or 'microservices'"""
    ms = arch == "microservices"
    d = Dashboard()
    # selectors
    app = f'architecture="{arch}"' + (', application=~"$service"' if ms else "")
    http = app + ', uri!~"/actuator.*"'
    ctr = 'name=~"$service"' if ms else 'name="ecommerce-mono"'
    by = "application" if ms else None          # per-service breakdown only for microservices
    grp = f"{by}, " if by else ""
    leg = "{{application}} " if by else ""

    def per(expr_inner, agg="sum"):
        return f"{agg} by ({by}) ({expr_inner})" if by else f"{agg}({expr_inner})"

    # ------------------------------------------------------------ run summary
    # One value per panel, computed over the whole selected time range: select the start and end
    # of a JMeter run (or open the dashboard with &from=<start ms>&to=<end ms>) to read that run's results.
    rng = "[$__range]"
    count = f"sum(increase(http_server_requests_seconds_count{{{http}}}{rng}))"
    lat = [{"color": "green", "value": None}, {"color": "orange", "value": 0.2}, {"color": "red", "value": 1}]
    d.row("Run summary (whole selected time range)")
    d.stat("Throughput (avg req/s)", f"{count} / $__range_s", "reqps", w=4, decimals=1, instant=True,
           desc="Requests handled by the server divided by the length of the selected time range. Select exactly one test run.")
    d.stat("Average response time", f"sum(increase(http_server_requests_seconds_sum{{{http}}}{rng})) / {count}", "s", w=4, instant=True,
           thresholds=lat, desc="Mean server-side processing time over the selected range (does not include the network trip to JMeter)")
    d.stat("p95 response time", f"histogram_quantile(0.95, sum by (le) (increase(http_server_requests_seconds_bucket{{{http}}}{rng})))", "s", w=4,
           instant=True, thresholds=lat, desc="95 % of requests in the selected range were faster than this (server side)")
    d.stat("p99 response time", f"histogram_quantile(0.99, sum by (le) (increase(http_server_requests_seconds_bucket{{{http}}}{rng})))", "s", w=4,
           instant=True, thresholds=lat, desc="99 % of requests in the selected range were faster than this (server side)")
    d.stat("Requests (total)", count, "short", w=4, decimals=0, instant=True, desc="Requests handled by the server in the selected range")
    d.stat("Errors (5xx)", f'(sum(increase(http_server_requests_seconds_count{{{http}, status=~"5.."}}{rng})) or vector(0)) / {count}',
           "percentunit", w=4, instant=True,
           thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 0.01}, {"color": "red", "value": 0.05}],
           desc="Server errors only: requests refused or timed out before reaching the application are counted by JMeter, not here")

    # ------------------------------------------------------------ overview
    d.row("Overview")
    if ms:
        d.stat("Services up", f'sum(up{{job="microservices"}})', decimals=0, w=3,
               thresholds=[{"color": "red", "value": None}, {"color": "orange", "value": 1}, {"color": "green", "value": 3}])
    else:
        d.stat("Status", 'max(up{job="monolith"})', decimals=0, w=3,
               thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 1}])
    d.stat("Requests/s", f"sum(rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))", "reqps", decimals=1)
    d.stat("p95 latency", f"histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{{{http}}}[$__rate_interval])))",
           "s", thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 0.2}, {"color": "red", "value": 1}])
    d.stat("Error rate (5xx)",
           f'(sum(rate(http_server_requests_seconds_count{{{http}, status=~"5.."}}[$__rate_interval])) or vector(0)) / sum(rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))',
           "percentunit", thresholds=[{"color": "green", "value": None}, {"color": "orange", "value": 0.01}, {"color": "red", "value": 0.05}])
    d.stat("CPU (cores)", f"sum(rate(container_cpu_usage_seconds_total{{{ctr}}}[$__rate_interval]))", decimals=2)
    d.stat("Memory (working set)", f"sum(container_memory_working_set_bytes{{{ctr}}})", "bytes")
    d.stat("DB connections active", f"sum(hikaricp_connections_active{{{app}}})", decimals=0)
    d.stat("Uptime", f"min(process_uptime_seconds{{{app}}})", "s")

    # ------------------------------------------------------------ HTTP
    d.row("HTTP (REST API)")
    d.ts("Requests/s per endpoint",
         [q(f"sum by ({grp}method, uri) (rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))", leg + "{{method}} {{uri}}")], "reqps")
    d.ts("Response time: average, p50, p95, p99 (all endpoints)",
         [q(f"sum(rate(http_server_requests_seconds_sum{{{http}}}[$__rate_interval])) / sum(rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))", "avg")] +
         [q(f"histogram_quantile({p}, sum by (le) (rate(http_server_requests_seconds_bucket{{{http}}}[$__rate_interval])))", f"p{int(p * 100)}")
          for p in (0.5, 0.95, 0.99)], "s")
    d.ts("Average response time per endpoint",
         [q(f"sum by ({grp}method, uri) (rate(http_server_requests_seconds_sum{{{http}}}[$__rate_interval])) / sum by ({grp}method, uri) (rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))",
            leg + "{{method}} {{uri}}")], "s")
    d.ts("p95 latency per endpoint",
         [q(f"histogram_quantile(0.95, sum by (le, {grp}method, uri) (rate(http_server_requests_seconds_bucket{{{http}}}[$__rate_interval])))", leg + "{{method}} {{uri}}")], "s")
    d.ts("Responses per status",
         [q(f"sum by ({grp}status) (rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))", leg + "{{status}}")], "reqps", stack=True)
    if ms:
        d.ts("Requests/s per service", [q(f"sum by (application) (rate(http_server_requests_seconds_count{{{http}}}[$__rate_interval]))", "{{application}}")], "reqps")
        d.ts("p95 latency per service",
             [q(f"histogram_quantile(0.95, sum by (le, application) (rate(http_server_requests_seconds_bucket{{{http}}}[$__rate_interval])))", "{{application}}")], "s")

    # ------------------------------------------------------------ gRPC (microservices only)
    if ms:
        d.row("gRPC (service-to-service)")
        d.ts("Client calls/s (order-service -> user/product)",
             [q('sum by (net_peer_name, rpc_method, grpc_status_code) (rate(grpc_client_seconds_count{architecture="microservices"}[$__rate_interval]))',
                "-> {{net_peer_name}} {{rpc_method}} {{grpc_status_code}}")], "reqps")
        d.ts("Client latency (p50 / p95 / p99)",
             [q(f'histogram_quantile({p}, sum by (le, rpc_method) (rate(grpc_client_seconds_bucket{{architecture="microservices"}}[$__rate_interval])))',
                f"{{{{rpc_method}}}} p{int(p * 100)}") for p in (0.5, 0.95, 0.99)], "s",
             desc="Network + remote processing time seen by order-service")
        d.ts("Server calls/s",
             [q('sum by (application, rpc_method) (rate(grpc_server_seconds_count{architecture="microservices"}[$__rate_interval]))', "{{application}} {{rpc_method}}")], "reqps")
        d.ts("Server latency p95",
             [q('histogram_quantile(0.95, sum by (le, application, rpc_method) (rate(grpc_server_seconds_bucket{architecture="microservices"}[$__rate_interval])))',
                "{{application}} {{rpc_method}}")], "s", desc="Processing time inside user-service / product-service")
        d.ts("gRPC errors/s",
             [q('sum by (application, rpc_method, grpc_status_code) (rate(grpc_client_seconds_count{architecture="microservices", grpc_status_code!="OK"}[$__rate_interval]))',
                "{{application}} {{rpc_method}} {{grpc_status_code}}"),
              q('sum(rate(grpc_client_seconds_count{architecture="microservices", grpc_status_code!="OK"}[$__rate_interval])) or vector(0)', "total")],
             "reqps", w=24, h=6)

    # ------------------------------------------------------------ JVM
    d.row("JVM")
    d.ts("Heap used / max",
         [q(per(f'jvm_memory_used_bytes{{{app}, area="heap"}}'), leg + "used"),
          q(per(f'jvm_memory_max_bytes{{{app}, area="heap"}}'), leg + "max")], "bytes")
    d.ts("Non-heap used", [q(per(f'jvm_memory_used_bytes{{{app}, area="nonheap"}}'), leg + "non-heap")], "bytes")
    d.ts("GC pause time per second", [q(per(f"rate(jvm_gc_pause_seconds_sum{{{app}}}[$__rate_interval])"), leg + "gc")], "s")
    d.ts("Process CPU usage (of the container CPUs)", [q(per(f"process_cpu_usage{{{app}}}", "max"), leg + "process")], "percentunit")
    d.ts("Live threads", [q(per(f"jvm_threads_live_threads{{{app}}}"), leg + "threads")], "short")
    d.ts("Classes loaded", [q(per(f"jvm_classes_loaded_classes{{{app}}}"), leg + "classes")], "short")

    # ------------------------------------------------------------ database
    d.row("Database connection pool (HikariCP)")
    d.ts("Connections",
         [q(per(f"hikaricp_connections_active{{{app}}}"), leg + "active"),
          q(per(f"hikaricp_connections_idle{{{app}}}"), leg + "idle"),
          q(per(f"hikaricp_connections_pending{{{app}}}"), leg + "pending"),
          q(per(f"hikaricp_connections_max{{{app}}}"), leg + "max")], "short")
    d.ts("Connection acquire / usage time (avg)",
         [q(f"sum by ({by or 'pool'}) (rate(hikaricp_connections_acquire_seconds_sum{{{app}}}[$__rate_interval])) / sum by ({by or 'pool'}) (rate(hikaricp_connections_acquire_seconds_count{{{app}}}[$__rate_interval]))", leg + "acquire"),
          q(f"sum by ({by or 'pool'}) (rate(hikaricp_connections_usage_seconds_sum{{{app}}}[$__rate_interval])) / sum by ({by or 'pool'}) (rate(hikaricp_connections_usage_seconds_count{{{app}}}[$__rate_interval]))", leg + "usage")], "s")

    # ------------------------------------------------------------ container
    d.row("Container resources (cAdvisor)")
    cpu_leg = "{{name}}" if ms else "ecommerce-mono"
    cpu_targets = [q(f"sum by (name) (rate(container_cpu_usage_seconds_total{{{ctr}}}[$__rate_interval]))", cpu_leg),
                   q(f"sum by (name) (container_spec_cpu_quota{{{ctr}}} / container_spec_cpu_period{{{ctr}}})", cpu_leg + " limit")]
    mem_targets = [q(f"sum by (name) (container_memory_working_set_bytes{{{ctr}}})", cpu_leg),
                   q(f"sum by (name) (container_spec_memory_limit_bytes{{{ctr}}})", cpu_leg + " limit")]
    if ms:
        cpu_targets.append(q(f"sum(rate(container_cpu_usage_seconds_total{{{ctr}}}[$__rate_interval]))", "total (all services)"))
        mem_targets.append(q(f"sum(container_memory_working_set_bytes{{{ctr}}})", "total (all services)"))
    d.ts("CPU (cores) vs limit", cpu_targets, "short")
    d.ts("Memory working set vs limit", mem_targets, "bytes")
    d.ts("CPU throttling (s/s)", [q(f"sum by (name) (rate(container_cpu_cfs_throttled_seconds_total{{{ctr}}}[$__rate_interval]))", "{{name}}")], "s",
         desc="Time the container wanted CPU but was capped by its limit: >0 means the CPU limit is the bottleneck")
    d.ts("Network I/O",
         [q(f"sum by (name) (rate(container_network_receive_bytes_total{{{ctr}}}[$__rate_interval]))", "{{name}} rx"),
          q(f"-sum by (name) (rate(container_network_transmit_bytes_total{{{ctr}}}[$__rate_interval]))", "{{name}} tx")], "Bps")

    # ------------------------------------------------------------ shared infrastructure
    d.row("Shared infrastructure (PostgreSQL / host)")
    d.ts("PostgreSQL CPU (cores)", [q('sum(rate(container_cpu_usage_seconds_total{name="postgres_db"}[$__rate_interval]))', "postgres")], "short", w=8)
    d.ts("PostgreSQL memory", [q('sum(container_memory_working_set_bytes{name="postgres_db"})', "postgres")], "bytes", w=8)
    d.ts("Host CPU / memory (node-exporter)",
         [q('1 - avg(rate(node_cpu_seconds_total{mode="idle"}[$__rate_interval]))', "CPU"),
          q("1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes", "memory")], "percentunit", w=8,
         desc="Docker VM running all containers (and the load generator if it runs in Docker)")

    # ------------------------------------------------------------ logs
    d.row("Logs (Fluent Bit -> Loki)")
    lsel = f'job="spring-boot", architecture="{arch}"' + (', container=~"$service"' if ms else "")
    d.ts("Log lines/s per level", [q(f'sum by ({"container, " if ms else ""}level) (rate({{{lsel}}}[1m]))', ("{{container}} " if ms else "") + "{{level}}")],
         "short", w=24, h=6, ds=LOKI)
    d.logs("Application logs",
           f'{{{lsel}, level=~"$level"}} |~ "$search" | json | line_format "{{{{.container}}}} {{{{.level}}}} {{{{.logger_name}}}} - {{{{.message}}}}"')

    # ------------------------------------------------------------ variables
    variables = []
    if ms:
        variables.append({
            "name": "service", "label": "Service", "type": "custom",
            "query": "user-service,product-service,order-service",
            "includeAll": True, "multi": True, "allValue": "user-service|product-service|order-service",
            "current": {"text": ["All"], "value": ["$__all"]}, "options": []})
    variables += [
        {"name": "level", "label": "Log level", "type": "custom", "query": "ERROR,WARN,INFO,DEBUG,UNKNOWN",
         "includeAll": True, "multi": True, "allValue": ".*", "current": {"text": ["All"], "value": ["$__all"]}, "options": []},
        {"name": "search", "label": "Log search", "type": "textbox", "query": "", "current": {"text": "", "value": ""}},
    ]

    title = "Microservices" if ms else "Monolith"
    other = "monolith" if ms else "microservices"
    return {
        "uid": arch,
        "title": title,
        "description": f"Monitoring of the {arch} profile (docker compose --profile {arch})",
        "tags": ["performance", "spring-boot", arch],
        "timezone": "browser",
        "schemaVersion": 41,
        "version": 1,
        "refresh": "5s",
        "time": {"from": "now-15m", "to": "now"},
        "links": [{"title": f"Open the {other.capitalize()} dashboard", "type": "link", "url": f"/d/{other}", "icon": "dashboard"}],
        "templating": {"list": variables},
        "panels": d.panels,
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    old = OUT / "architecture-comparison.json"
    if old.exists():
        old.unlink()
    for arch in ("monolith", "microservices"):
        dash = build(arch)
        (OUT / f"{arch}.json").write_text(json.dumps(dash, indent=2), encoding="utf-8")
        print(f"wrote {arch}.json ({len(dash['panels'])} panels)")
