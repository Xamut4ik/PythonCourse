import string


def lenfunc(string):
    return len(string)

def constr(str1, str2):
    return str1 + str2
print(lenfunc("Добрий день"))
print(constr("Добрий день", "як справи?"))


def square(num):
    return num * num

def summary(num1, num2):
    return num1 + num2

def division(num1: int, num2: int):
    return num1 / num2

print(square(10))
print(summary(10, 10))
print(division(10, 3))


def average(list):
    return sum(list) / len(list)

def genval(list1, list2):
    list3 = list1 + list2
    dublicates = []
    for num in list3:
        if list3.count(num) > 1 and num not in dublicates:
            dublicates.append(num)
    return dublicates


print(average([1, 4, 5, 2]))
print(genval([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [2, 4, 6, 1, 10]))


def keys(dict):
    return dict.keys()

def comdict(dict1, dict2):
    return dict1 | dict2

print(keys(dict(a=1, b=2, c=3)))
print(comdict(dict(a=1, b=2, c=3), dict(a=1, b=2, c=4)))


def comset(set1, set2):
    return set1 | set2

def setverf(set1, set2):
    if set1.issubset(set2) or set2.issubset(set1):
        print("Множина є підмножиною іншої")
    else:
        print("Множина не є підмножиною іншої")


print(comset({2, 3, 1}, {1, 6, 4}))
setverf({1, 3, 2}, {1, 3, 5})


def pairnum(num1):
    if num1 % 2 == 0:
        print("Число парне")
    else:
        print("Число непарне")

def pairlistnum(list1):
    list2 = []
    for i in list1:
        if i % 2 == 0:
            list2.append(i)
            i+=1
        else:
            pass
    return list2

pairnum(5)
print(pairlistnum([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))


pairnumber = lambda num: "Парне" if num % 2 == 0 else "Непарне"

print(pairnumber(4))


