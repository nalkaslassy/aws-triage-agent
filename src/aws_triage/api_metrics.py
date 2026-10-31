"""REST API customer-facing metrics, with a preceding equal-length baseline."""


SPECS = (("requests", "Count", ["SampleCount"]),
         ("server_errors", "5XXError", ["Sum"]),
         ("client_errors", "4XXError", ["Sum"]),
         ("latency_ms", "Latency", ["Sum", "SampleCount"]),
         ("integration_latency_ms", "IntegrationLatency", ["Sum", "SampleCount"]))


def collect_api_metrics(collector, api):
    duration = collector.end - collector.start
    resource = f"{api['api_name']}/{api['stage']} ({api['api_id']})"
    for window, start, end in (("incident", collector.start, collector.end),
                               ("baseline", collector.start - duration, collector.start)):
        data = {"window": window, "start": start.isoformat(), "end": end.isoformat(),
                "api_id": api["api_id"], "api_name": api["api_name"], "stage": api["stage"]}
        failures, successes = [], 0
        for name, metric, stats in SPECS:
            try:
                response = collector.call("cloudwatch", "get_metric_statistics", Namespace="AWS/ApiGateway",
                                          MetricName=metric, Dimensions=[{"Name": "ApiName", "Value": api["api_name"]},
                                                                         {"Name": "Stage", "Value": api["stage"]}],
                                          StartTime=start, EndTime=end, Period=60, Statistics=stats)
                points = response.get("Datapoints", [])
                if not points:
                    data[name] = None
                elif name.endswith("latency_ms"):
                    count = sum(p["SampleCount"] for p in points)
                    data[name] = sum(p["Sum"] for p in points) / count if count > 0 else None
                else:
                    data[name] = sum(p[stats[0]] for p in points)
                successes += 1
            except Exception as error:
                data[name] = None
                failures.append(f"{metric}: {collector.error_code(error)}")
        if failures:
            data["reason"] = "Some API metrics could not be read: " + ", ".join(failures)
        collector.add("api_metrics", resource, "cloudwatch:GetMetricStatistics", data,
                      "partial" if failures and successes else "unavailable" if failures else "observed")
