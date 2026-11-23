"""Check the Obsidian links and required sections used by this vault."""
from collections import defaultdict, deque
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOP_NAMES = "冲奶与消毒 奶量与判断 拍嗝与吐奶 安全睡眠 包裹与哄睡 换尿布与红屁屁 洗澡与脐带 呛奶急救 就医信号 伤口与恶露 回奶 情绪与EPDS".split()
SOP_SECTIONS = "一句话结论 适用条件 需要准备的物品 标准操作步骤 正确完成的判断方法 常见错误 风险与禁忌 何时咨询医生或立即就医 参考来源与核查日期 关联笔记".split()
LESSON_FIELDS = "学习目标 建议时间 必须掌握 操作 常见错误与安全 练习与验收 权威资料和笔记".split()
HEADING = re.compile(r"^#{1,6} +(.+)$", re.M)
WIKI = re.compile(r"\[\[([^\]|\n]+)(?:\|[^\]\n]+)?\]\]")
MARKDOWN = re.compile(r"(?<!!)\[[^\[\]\n]+\]\(([^)\n]+)\)")
PRIVATE = {"private", ".git", ".obsidian", ".trash"}


def reachable(graph, start):
    distances = {start: 0}
    remaining = deque([start])
    while remaining:
        node = remaining.popleft()
        for neighbor in graph[node] - distances.keys():
            distances[neighbor] = distances[node] + 1
            remaining.append(neighbor)
    return distances


def main():
    files = {
        path.relative_to(ROOT): path.read_text(encoding="utf-8-sig")
        for path in ROOT.rglob("*.md")
        if not PRIVATE.intersection(path.relative_to(ROOT).parts)
    }
    names = defaultdict(list)
    for path in files:
        names[path.stem].append(path)
    errors = []
    graph = defaultdict(set)
    sources = set()
    link_count = 0
    for name, paths in names.items():
        if len(paths) > 1:
            errors.append(f"重名文件 {name}: {paths}")
    for path, body in files.items():
        headings = HEADING.findall(body)
        if len(headings) != len(set(headings)):
            errors.append(f"{path}: 重复章节")
        sources.update(ref for ref in MARKDOWN.findall(body) if ref.startswith("https://"))
        for ref in WIKI.findall(body):
            link_count += 1
            target, _, anchor = ref.partition("#")
            matches = ([path] if not target else names.get(target, []))
            if "/" in target:
                matches = [Path(target.removesuffix(".md") + ".md")]
            if len(matches) != 1 or matches[0] not in files:
                errors.append(f"{path}: 无法解析 [[{ref}]]")
                continue
            dest = matches[0]
            if anchor and anchor not in HEADING.findall(files[dest]):
                errors.append(f"{path}: 找不到标题 [[{ref}]]")
            graph[path].add(dest)
        for ref in MARKDOWN.findall(body):
            url = urlsplit(ref)
            if url.scheme:
                if url.scheme not in {"http", "https"} or not url.netloc:
                    errors.append(f"{path}: 异常 URL {ref}")
                continue
            link_count += 1
            dest = (ROOT / path.parent / unquote(url.path)).resolve() if url.path else ROOT / path
            if not dest.is_relative_to(ROOT) or not dest.is_file():
                errors.append(f"{path}: 无效相对路径 {ref}")
                continue
            relative = dest.relative_to(ROOT)
            if relative in files:
                graph[path].add(relative)
                if url.fragment:
                    slugs = [re.sub(r"[^\w -]", "", h.lower()).replace(" ", "-")
                             for h in HEADING.findall(files[relative])]
                    if unquote(url.fragment) not in slugs:
                        errors.append(f"{path}: 无效 Markdown 锚点 {ref}")
        if path.stem in SOP_NAMES:
            sections = re.findall(r"^## (.+)$", body, re.M)
            if sections != SOP_SECTIONS:
                errors.append(f"{path}: SOP 章节缺失或顺序不一致")
            reference = body.partition("## 参考来源与核查日期")[2].split("\n## ", 1)[0]
            if "https://" not in reference or not re.search(r"\d{4}-\d{2}-\d{2}", reference):
                errors.append(f"{path}: 缺少来源或核查日期")

    if set(SOP_NAMES) - names.keys():
        errors.append("缺少核心 SOP 文件")
    distances = reachable(graph, Path("首页.md"))
    for path in files:
        if path != Path("README.md") and path not in distances:
            errors.append(f"{path}: 首页不可达")
        if path.stem in SOP_NAMES and distances.get(path, 999) > 3:
            errors.append(f"{path}: 超过三次点击")
    course = next((body for path, body in files.items() if path.stem == "六周上岗计划"), "")
    lessons = re.split(r"^## 第[一二三四]周 · .+$", course, flags=re.M)[1:]
    if len(lessons) != 4 or any(any(field not in lesson for field in LESSON_FIELDS) for lesson in lessons):
        errors.append("四周课程字段不全")
    if not course or distances.get(names["六周上岗计划"][0], 999) > 3:
        errors.append("产前课程入口不可达")
    markers = sum(body.count("待核实") for body in files.values())
    print(f"{len(files)} 篇 Markdown；{link_count} 条内部链接；{len(SOP_NAMES)} 篇核心 SOP；"
          f"{len(lessons)} 周课程；{len(sources)} 个 HTTPS 来源；{markers} 处待核实字样")
    print(f"首页覆盖 {len(distances)} 篇；核心 SOP 最多 {max((distances.get(p, 0) for p in files if p.stem in SOP_NAMES), default=0)} 次点击")
    for error in errors:
        print(error)
    print(f"{len(errors)} 个结构错误")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
