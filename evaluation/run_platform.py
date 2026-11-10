"""Read-only evaluation of the Singapore HTTPS edge and VPC configuration.

The optional Cloud Armor probe sends one GET with a synthetic SQLi query to a public,
read-only API and checks the corresponding load-balancer log. No production policy or
application resource is modified.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


BACKENDS = {
    "configuration-service": "/api/auth/subscription-tiers/",
    "messaging-ingester": "/messaging/",
    "payment-ingester": "/payment/",
    "mock-whatsapp": "/whatsapp/",
}
PATHS = {
    "/payment/*": "payment-ingester",
    "/messaging/*": "messaging-ingester",
    "/whatsapp/*": "mock-whatsapp",
    "/config/*": "configuration-service",
}


def gcloud(project: str, *args: str) -> dict | list:
    executable = shutil.which("gcloud.cmd" if os.name == "nt" else "gcloud")
    if not executable:
        raise RuntimeError("gcloud CLI not found on PATH")
    command = [executable, *args, f"--project={project}", "--format=json"]
    completed = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=40)
    if completed.returncode:
        raise RuntimeError(f"{' '.join(args)}: {completed.stderr.strip()[-500:]}")
    return json.loads(completed.stdout)


def get(url: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], float]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, response_headers = response.status, dict(response.headers)
            response.read()
    except urllib.error.HTTPError as exc:
        status, response_headers = exc.code, dict(exc.headers)
        exc.close()
    return status, response_headers, round((time.perf_counter() - started) * 1000, 1)


def record(results: list[dict], name: str, passed: bool, detail: str, **observed) -> None:
    results.append({"name": name, "status": "pass" if passed else "fail", "detail": detail, **observed})
    print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}", flush=True)


def backend_name(link: str) -> str:
    return link.rsplit("/", 1)[-1]


def inspect(project: str, region: str, host: str, expected_ip: str, results: list[dict]) -> dict:
    rule = gcloud(project, "compute", "forwarding-rules", "describe", "serverless-https-forwarding-rule", "--global")
    proxy = gcloud(project, "compute", "target-https-proxies", "describe", "serverless-https-proxy", "--global")
    url_map = gcloud(project, "compute", "url-maps", "describe", "serverless-url-map", "--global")
    cert = gcloud(project, "compute", "ssl-certificates", "describe", "ansera-managed-cert", "--global")
    armor = gcloud(project, "compute", "security-policies", "describe", "armor-policy", "--global")
    if isinstance(armor, list):
        armor = next(item for item in armor if item.get("name") == "armor-policy")
    subnet = gcloud(project, "compute", "networks", "subnets", "describe", "default", f"--region={region}")
    nat = gcloud(project, "compute", "routers", "nats", "describe", "messaging-nat-gateway",
                 "--router=messaging-nat-router", f"--region={region}")

    ip = rule.get("IPAddress")
    record(results, "HTTPS forwarding", ip == expected_ip and rule.get("portRange") in {"443", "443-443"}
           and backend_name(rule.get("target", "")) == "serverless-https-proxy",
           f"{ip}:443 -> {backend_name(rule.get('target', ''))}")
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    record(results, "DNS to load balancer", expected_ip in addresses,
           f"{host} resolves to {', '.join(sorted(addresses))}")
    record(results, "HTTPS proxy and certificate",
           backend_name(proxy.get("urlMap", "")) == "serverless-url-map"
           and any(backend_name(item) == "ansera-managed-cert" for item in proxy.get("sslCertificates", []))
           and cert.get("managed", {}).get("status") == "ACTIVE"
           and host in cert.get("managed", {}).get("domains", []),
           f"certificate {cert.get('managed', {}).get('status')} for {host}")

    matcher = next((item for item in url_map.get("pathMatchers", []) if item.get("name") == "main-paths"), {})
    actual_paths = {path: (backend_name(rule.get("service", "")),
                            rule.get("routeAction", {}).get("urlRewrite", {}).get("pathPrefixRewrite"))
                    for rule in matcher.get("pathRules", []) for path in rule.get("paths", [])}
    expected_paths = {path: (f"backend-{service}", "/") for path, service in PATHS.items()}
    record(results, "URL map and prefix rewrites",
           actual_paths == expected_paths
           and backend_name(matcher.get("defaultService", "")) == "backend-configuration-service",
           "four expected prefixed backends; /api/* defaults to configuration-service",
           routes=actual_paths)

    policy_name = armor.get("name")
    for service in BACKENDS:
        backend = gcloud(project, "compute", "backend-services", "describe", f"backend-{service}", "--global")
        neg = gcloud(project, "compute", "network-endpoint-groups", "describe", f"neg-{service}",
                     f"--region={region}")
        logging = backend.get("logConfig", {})
        record(results, f"{service} backend", backend_name(backend.get("securityPolicy", "")) == policy_name
               and logging.get("enable") is True and logging.get("sampleRate") == 1
               and neg.get("cloudRun", {}).get("service") == service,
               "serverless NEG, Cloud Armor attachment, 100% backend logging")

    rules = {rule.get("priority"): rule for rule in armor.get("rules", [])}
    waf = {1000: "sqli", 1100: "xss", 1200: "lfi", 1300: "rce"}
    waf_expected = all(rules.get(priority, {}).get("preview") is True
                       and rules.get(priority, {}).get("action") == "deny(403)"
                       and family in rules.get(priority, {}).get("match", {}).get("expr", {}).get("expression", "")
                       for priority, family in waf.items())
    default = rules.get(2147483647, {})
    record(results, "Cloud Armor policy mode", waf_expected and default.get("action") == "allow",
           "SQLi/XSS/LFI/RCE are preview-only; default action is allow",
           blocking_enabled=False)

    subnet_link = subnet.get("selfLink", "")
    nat_subnets = nat.get("subnetworks", [])
    record(results, "Private Google Access and NAT", subnet.get("privateIpGoogleAccess") is True
           and any(item.get("name") == subnet_link and "PRIMARY_IP_RANGE" in item.get("sourceIpRangesToNat", [])
                   for item in nat_subnets),
           "Singapore default subnet has Private Google Access and primary-range Cloud NAT")

    callers = {}
    for service in ("configuration-service", "messaging-service", "mock-whatsapp",
                    "messaging-ingester", "processing-service", "payment-ingester"):
        run = gcloud(project, "run", "services", "describe", service, f"--region={region}")
        annotations = run.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {})
        metadata = run.get("metadata", {}).get("annotations", {})
        env = run.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("env", [])
        callers[service] = {
            "ingress": metadata.get("run.googleapis.com/ingress"),
            "vpc_egress": annotations.get("run.googleapis.com/vpc-access-egress"),
            "network_interfaces": annotations.get("run.googleapis.com/network-interfaces"),
            "run_url": run.get("status", {}).get("url"),
            "configuration_url": next((item.get("value") for item in env
                                       if item.get("name") == "CONFIGURATION_SERVICE_URL"), None),
            "ready": next((item.get("status") for item in run.get("status", {}).get("conditions", [])
                           if item.get("type") == "Ready"), None),
        }
    for service in ("configuration-service", "messaging-service", "mock-whatsapp"):
        item = callers[service]
        record(results, f"{service} VPC path", item["ready"] == "True" and item["vpc_egress"] == "all-traffic"
               and '"network":"default"' in (item["network_interfaces"] or ""),
               f"ready={item['ready']}, egress={item['vpc_egress']}, ingress={item['ingress']}")
    for service, item in callers.items():
        status, _, _ = get(item["run_url"] + BACKENDS.get(service, "/"))
        record(results, f"{service} direct ingress", status == 404,
               f"external GET to run.app returned HTTP {status}")
    job = gcloud(project, "run", "jobs", "describe", "notification-job", f"--region={region}")
    job_spec = job.get("spec", {}).get("template", {})
    job_env = job_spec.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])[0].get("env", [])
    callers["notification-job"] = {
        "vpc_egress": job_spec.get("metadata", {}).get("annotations", {}).get("run.googleapis.com/vpc-access-egress"),
        "configuration_url": next((item.get("value") for item in job_env
                                   if item.get("name") == "CONFIGURATION_SERVICE_URL"), None),
    }
    for service in ("messaging-service", "messaging-ingester", "processing-service", "notification-job"):
        item = callers[service]
        url = urllib.parse.urlsplit(item["configuration_url"] or "")
        via_lb = url.scheme == "https" and url.hostname in {host, "34-149-82-198.sslip.io"} and url.path == "/api"
        direct = url.scheme == "https" and url.hostname == urllib.parse.urlsplit(
            callers["configuration-service"]["run_url"]).hostname and url.path == "/api"
        record(results, f"{service} configuration route", via_lb or direct and item["vpc_egress"] == "all-traffic",
               f"route={'load balancer' if via_lb else 'direct run.app' if direct else 'unknown'}, "
               f"VPC egress={item['vpc_egress'] or 'none'}")
    return {"cloud_run_networking": callers, "cloud_armor_mode": "preview_only"}


def probe_routes(base: str, results: list[dict]) -> None:
    for service, path in BACKENDS.items():
        status, _, latency = get(base + path)
        record(results, f"{service} HTTPS route", status == 200,
               f"GET {path}: HTTP {status}, {latency} ms", latency_ms=latency)
    status, _, latency = get(base + "/config/api/auth/subscription-tiers/")
    record(results, "configuration prefix rewrite", status == 200,
           f"GET /config/api/auth/subscription-tiers/: HTTP {status}, {latency} ms", latency_ms=latency)
    # A valid TLS handshake and hostname check are performed by urllib's default HTTPS context.
    record(results, "trusted HTTPS", True, "all route probes used verified HTTPS")


def probe_armor(project: str, base: str, results: list[dict], wait_seconds: int) -> None:
    marker = "evalarmor" + uuid.uuid4().hex[:12]
    query = urllib.parse.urlencode({"eval_marker": marker, "q": "1' OR '1'='1"})
    status, _, latency = get(base + "/api/auth/subscription-tiers/?" + query)
    record(results, "Cloud Armor preview response", status == 200,
           f"synthetic SQLi GET: HTTP {status}, {latency} ms; preview must not deny")
    deadline = time.monotonic() + wait_seconds
    found = None
    while time.monotonic() < deadline:
        logs = gcloud(project, "logging", "read",
                      f'resource.type="http_load_balancer" AND httpRequest.requestUrl:"{marker}"',
                      "--freshness=10m", "--limit=10")
        if logs:
            found = logs[0]
            break
        time.sleep(5)
    if found is None:
        record(results, "Cloud Armor request log", False, f"no matching LB log within {wait_seconds}s")
        return
    policy = found.get("jsonPayload", {})
    enforced = policy.get("enforcedSecurityPolicy", {})
    preview = policy.get("previewSecurityPolicy", {})
    record(results, "Cloud Armor request log", enforced.get("name") == "armor-policy",
           f"enforced={enforced.get('outcome')}, preview={preview.get('configuredAction', 'none')}",
           preview_matched=bool(preview), preview_priority=preview.get("priority"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="cs5224-ansera")
    parser.add_argument("--region", default="asia-southeast1")
    parser.add_argument("--host", default="ansera.hopto.org")
    parser.add_argument("--expected-ip", default="34.149.82.198")
    parser.add_argument("--armor-probe", action="store_true", help="Send one synthetic SQLi GET and inspect LB logs")
    parser.add_argument("--log-wait-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "results" / "platform.json")
    args = parser.parse_args()
    results: list[dict] = []
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "project": args.project,
              "host": args.host, "checks": results}
    try:
        report.update(inspect(args.project, args.region, args.host, args.expected_ip, results))
        base = f"https://{args.host}"
        probe_routes(base, results)
        if args.armor_probe:
            probe_armor(args.project, base, results, args.log_wait_seconds)
    except Exception as exc:
        record(results, "runner completion", False, f"{type(exc).__name__}: {exc}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Results: {args.output.resolve()}")
    return 0 if results and all(item["status"] == "pass" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
