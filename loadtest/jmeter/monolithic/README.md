# JMeter tests — monolith

Three test plans for the monolithic application (`ecommerceMono`), one file per test:

| File | Test | What it shows |
|---|---|---|
| `load-test.jmx` | Load test | Users added continuously until the server breaks: how latency and errors grow, and when requests start being refused |
| `scalability-test.jmx` | Scalability test | Users added in plateaus: throughput and latency at each load level, and the step where the server stops scaling and fails |
| `spike-test.jmx` | Spike test | A sudden flash-sale burst on top of normal traffic: does it knock the server over, and does it recover afterwards |

**Goal: break the server.** Each test lasts at most 5 minutes and its defaults push load high enough to reach the point where the server refuses or times out on (almost) every request.
All three run the same shopping workload, so their results can be compared.

## The server is not hard-coded

`HOST` is **empty** in every file. Give the server one of two ways:

- **Command line (recommended):** `-Jhost=<server address>` and, if needed, `-Jport=<port>` (default `8080`) and `-Jprotocol=https` (default `http`).
- **JMeter GUI:** open the file and fill `HOST` in the **"Server and test settings"** element at the top.

`host` is only the address (for example `192.168.1.50` or `my-vm.example.com`), without `http://`.
If no server is given, the test stops right away with the message `No server set`.

Property names (`host`, `port`, `users`, `ramp`, `duration`, `think_time`, `run_id`) follow the JMeter configuration contract on the workshop Notion page.

## Workload (same in all three tests)

Before the test, a setUp step checks the server, then creates `seed_users` users (one per virtual user: 1500, or 1550 for the spike test) and `seed_products` products (default 50), using `seed_threads` (default 20) threads in parallel so seeding stays short over the long Tunisia → Sweden link. Seeding is not part of the 5 minutes.
Each virtual user always uses its own seeded user, so carts are never shared between threads.

Each iteration is one of three scenarios, chosen deterministically so reruns send the same requests:

| Scenario | Share (default) | Requests |
|---|---|---|
| Browse | 80 % (`browse_pct`) | `GET /api/v1/products`, `GET /api/v1/products/search?keyword=product` |
| Product detail | 15 % (`detail_pct`) | `GET /api/v1/products/{id}`, `GET /api/v1/users/{id}` |
| Order | the rest (5 %) | 2 × `POST /api/v1/carts`, `GET /api/v1/carts`, `POST /api/v1/orders` |

After each iteration a user waits `think_time` milliseconds (default 100, kept short to put pressure on the server).
To run without writing orders (for example against production), use `-Jbrowse_pct=85 -Jdetail_pct=15`.

## Commands

Run JMeter in non-GUI mode for real measurements. Commands are run from the repository root.
The `sample_filter` option keeps the setUp requests out of the HTML report.

**Linux / macOS**
```bash
jmeter -n -t loadtest/jmeter/monolithic/load-test.jmx \
  -Jhost=<server address> -Jport=8080 -Jrun_id=team1-monolith-load \
  -l loadtest/jmeter/results/monolith-load/results.jtl \
  -e -o loadtest/jmeter/results/monolith-load/report \
  -Jjmeter.reportgenerator.sample_filter="^(?!setup).*"
```

**Windows (PowerShell)**
```powershell
jmeter.bat -n -t loadtest\jmeter\monolithic\load-test.jmx `
  -Jhost=<server address> -Jport=8080 -Jrun_id=team1-monolith-load `
  -l loadtest\jmeter\results\monolith-load\results.jtl `
  -e -o loadtest\jmeter\results\monolith-load\report `
  "-Jjmeter.reportgenerator.sample_filter=^(?!setup).*"
```

For the other tests, change the file name (`scalability-test.jmx`, `spike-test.jmx`) and the results folder.
JMeter needs an empty or new folder for `-o`, so use a new folder for every run.

## Configuration

Every value can be changed with `-J<name>=<value>`.

**All tests**

| Property | Default | Meaning |
|---|---|---|
| `host` | *(empty)* | Server address — required |
| `run_id` | `monolith-<date-time>` | Label of the run (written to `jmeter.log`); use e.g. `team1-monolith-v1.0.0-load-proxmox` |
| `port` | `8080` | Server port |
| `protocol` | `http` | `http` or `https` |
| `think_time` | `100` | Pause after each iteration (ms) |
| `response_timeout` | `10000` | A request with no answer after this many ms counts as failed |
| `connect_timeout` | `5000` | A connection not accepted within this many ms counts as failed |
| `browse_pct` / `detail_pct` | `80` / `15` | Scenario mix; order gets the rest |
| `seed_users` / `seed_products` | `1500` (spike: `1550`) / `50` | Data created by the setUp step; keep `seed_users` ≥ the maximum number of users |
| `seed_threads` | `20` | Parallel threads used for seeding |

**Load test** — `load-test.jmx`

| Property | Default | Meaning |
|---|---|---|
Users are added at a constant rate for the whole test: 0 → 1,500 users over 5 minutes (5 new users per second).

| Property | Default | Meaning |
|---|---|---|
| `users` | `1500` | Users reached at the end of the ramp |
| `ramp` | `300` | Seconds to reach `users` |
| `duration` | `300` | Total test length in seconds |

**Scalability test** — `scalability-test.jmx`

5 steps: every `step_seconds`, another `step_users` users join (default 300 → 600 → 900 → 1,200 → 1,500 users, 1 minute each, 5 minutes in total).

| Property | Default | Meaning |
|---|---|---|
| `step_users` | `300` | Users added at each step |
| `step_seconds` | `60` | Length of each step |
| `step_ramp` | `10` | Seconds to start the users of one step |

**Spike test** — `spike-test.jmx`

`base_users` shop for the whole test. At `spike_start`, `spike_users` more arrive within `spike_ramp` seconds, stay for `spike_hold` seconds and leave; the rest of the test shows recovery.
Default timeline: 0–60 s baseline (50 users) · 60–70 s spike ramp · 70–190 s spike (1,550 users) · 190–300 s recovery (50 users).

| Property | Default | Meaning |
|---|---|---|
| `base_users` | `50` | Users present for the whole test |
| `duration` | `300` | Total test length in seconds |
| `spike_users` | `1500` | Extra users during the spike |
| `spike_start` | `60` | Seconds before the spike starts |
| `spike_ramp` | `10` | Seconds for the spike users to arrive |
| `spike_hold` | `120` | Seconds the spike users stay |

## Reading the breaking point

In the HTML report, open **Charts → Over Time**: *Active Threads Over Time*, *Response Times Over Time* and *Transactions per Second* (successes vs failures).
The breaking point is where successful transactions per second stop rising and failures take over: connection refused, connect timeout, or no answer within `response_timeout`.
Write down the number of active users at that moment.

## Target server and sizing

The tests are sized for the workshop's **Azure VM** (`vm-performance-lab`, Standard_D4s_v4: 4 vCPU, 16 GiB RAM, Ubuntu Server 24.04, Sweden Central), running the monolith with `docker compose --profile monolith up -d`.
On that VM, Docker Compose limits the monolith container to **3 CPUs and 3 GiB** by default (`MONO_CPUS`, `MONO_MEMORY` in `docker-compose.yaml`), and Spring Boot uses its defaults: 200 Tomcat worker threads and 10 database connections.
These limits, not the 16 GiB of the VM, are what the server runs out of first.

- **Network path:** JMeter runs from Tunisia and the VM is in Sweden, so every response time includes the round trip between them. Compare runs made from the same place only.
- **Firewall:** the VM's network security group only allows SSH at first. Open the application port (8080) to your own public IP only, never to everyone, and close it after the session.
- **Why 1,500 users:** with 100 ms think time and the round trip to Sweden, each user sends a few requests per second, so a few hundred users already saturate 3 CPUs. Past that point, latency keeps growing until requests exceed `response_timeout` (10 s) and fail. 1,500 users are meant to push well past saturation within 5 minutes.
- **If the server has not broken** by the end of a run, raise `users`, `step_users` or `spike_users`, or lower `think_time`. If it breaks within seconds, lower them so the climb stays visible.
- **The load generator can break first:** 1,500 threads on one laptop, over a home or campus connection, can hit the laptop's CPU or upload bandwidth before the server's limits. Watch the laptop's CPU and network during the run. If they are the bottleneck, split the users across two JMeter machines.

These are starting points, not capacity claims: the breaking point is what the runs will measure.
Do a short smoke run first (for example `-Jusers=2 -Jramp=10 -Jduration=30` with the load test).

JMeter needs more memory than its default for 1,500 threads: start it with a bigger heap, for example `HEAP="-Xms1g -Xmx3g"` on Linux or `set HEAP=-Xms1g -Xmx3g` on Windows.
