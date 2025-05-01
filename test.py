def main():
    message = None
    with open("test1.txt", "r") as inPut:
        text_in = inPut.read()
        message = text_in.replace("\\n", "\n")
        message = message.replace('\\"', '"')

    with open("test2.txt", "w") as outPut:
        outPut.write(message)

main()