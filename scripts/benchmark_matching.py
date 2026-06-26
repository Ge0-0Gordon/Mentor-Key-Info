import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from match_mentors import run_match

MENTORS = Path("outputs/runs/simple_full_run_20260625_123834/mentor_results.jsonl")

QUERIES = [
    "我是留学生，想找互联网产品经理，目标字节美团，需要简历优化和模拟面试",
    "我是应届生，想投阿里腾讯的数据分析岗位，需要职业规划和面试辅导",
    "我在职想转行做新能源车企产品经理，目标蔚来理想小鹏，希望导师帮我改简历",
    "我想找金融行业投行或券商实习，需要简历优化和面试训练",
    "我是海归硕士，想做咨询或战略岗，目标 MBB 或互联网战略，需要 case 面试辅导",
    "我想找HRBP方向工作，希望导师懂招聘、人才发展和组织发展",
    "我是美硕new grad，目标大厂校招，想了解招聘标准和求职规划",
    "我想转产品运营方向，需要岗位定位、简历修改、模拟面试",
    "我想找AI大模型相关岗位，希望导师有互联网或人工智能行业背景",
    "我是职场人想跳槽到小红书或B站，方向是内容运营和增长运营",
]


def main() -> int:
    run_match(mentors_path=MENTORS, query=QUERIES[0], top_k=5)
    latencies = []
    for i in range(100):
        query = QUERIES[i % len(QUERIES)]
        started = time.perf_counter()
        run_match(mentors_path=MENTORS, query=query, top_k=5)
        latencies.append((time.perf_counter() - started) * 1000)
    print("runs:", len(latencies))
    print("avg_ms:", round(statistics.mean(latencies), 2))
    print("median_ms:", round(statistics.median(latencies), 2))
    print("p95_ms:", round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 2))
    print("min_ms:", round(min(latencies), 2))
    print("max_ms:", round(max(latencies), 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
