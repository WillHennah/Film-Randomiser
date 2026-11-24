import random as rm

## ask who had the last film choice

last = input('Who had the last film choice?    ')
last = last.capitalize()

## create lists of people and films

fam_list = ['Aimi', 'Miilo', 'Will', 'Henna']
film_list = ['first', 'second', 'third', 'forth']

## remove the person who had the last choice

fam_list.remove(last)

## Randomly select a family member and their film by position

Selector = rm.choice(fam_list)
Film = rm.choice(film_list)

## print the selection
print ()
print("The family film this week is...")
print(Selector + "\'s "  + Film + " choice!")
print()
 
 
 
### can we import the list of films and identify the selections film name to add to output?

famfilm_dict = {
"Will first": "Strangers on a Train",
"Will second": "My Life As A Dog",
"Will third": "clockwise/fish called wanda",
"Will forth": "Bond, James Bond...    Quantum of Solace",
"Henna first": "?",
"Henna second": "?",
"Henna third": "Harry Potter and the Deathly Hallows pt2",
"Henna forth": "Barbie",
"Miilo first": "The Films of Pixar...    Cars 3",
"Miilo second": "The Classic Films of Disney...    Alladin",
"Miilo third": "The Modern Films of Disney...   Lion King",
"Miilo forth": "Pirates of the Caribean 5",
"Aimi first": "The Films of Wes Andersen",
"Aimi second": "The Hunger Games 3 part 2",
"Aimi third": "High School Musical 2",
"Aimi forth": "Lord of the Rings...    The Return of the King"
}

Choice = Selector + ' ' + Film

print("   " + famfilm_dict[Choice])