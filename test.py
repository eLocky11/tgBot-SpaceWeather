import re

remove = ("Links to", "Community Coordinated Modeling", "Message Issue Date", "Disclaimer", "Message Type", "Message ID")

def test():
    content = None
    with open("test1.txt", "r", encoding="utf-8") as file1:
        content = file1.read()

    content = content.replace("\\n", "\n")
    content = content.replace("#", "")
    # content = re.sub(r"\n{2,}", "\n", content)

    lines = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith(remove):
            # continue
            pass
        if line == "Summary:":
            line = "Сводка:"
        if line == "Notes:":
            line = "Примечания:"
        if line.startswith("Activity ID"):
            lines.append(line)
            lines.append("")
            continue
        lines.append(line)
    content = "\n".join(lines).strip()

    with open("test2.txt", "w", encoding="utf-8") as file2:
        file2.write(content)

if __name__ == "__main__":
    test()