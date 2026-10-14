import math



def human_format(number):
    units = ['', 'K', 'M', 'B', 'T']
    k = 1000.0

    if not number:
        number = 0

    try:
        magnitude = int(math.floor(math.log(number + 1e-8, k)))

        x = number / (k ** magnitude)

        v = int(x) if int(x) == x else round(x, 3)

        return f"{v}{units[magnitude]}"
    except ValueError:
        return "0"


