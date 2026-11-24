import os
import pandas as pd
import random as rm
import datetime
import csv
import time
from datetime import date

#Load file tracking the Watched Films

os.chdir('/storage/emulated/0/Will_Files/Will Vault/Coding/Family Film Randomiser/')

watched = pd.read_csv('watched_films.csv')

#Print Last Chooser

last = watched['Chooser'].tail(1).item()
lastfilm = watched['Name'].tail(1).item()
lastdate = watched['Watched Date'].tail(1).item()
print('The last choice belonged to: ')
time.sleep(0.5)
print('   ', last)
print(' ')
time.sleep(0.9)
print('The last film was: ', )
time.sleep(0.5)
print('   ', lastfilm)
time.sleep(0.5)
print(' ')
print('          watched on', lastdate)
print(' ')
print(' ')
time.sleep(0.9)

#Calculate and Print Totals

will = watched['Chooser'].value_counts().get('William', 0)
henna = watched['Chooser'].value_counts().get('Henna', 0)
miilo = watched['Chooser'].value_counts().get('Miilo', 0)
aimi = watched['Chooser'].value_counts().get('Aimi', 0)
recent = watched['Chooser'].value_counts().get('Recent', 0)
other = watched['Chooser'].value_counts().get('Other', 0)
total = will + henna + miilo + aimi + other + recent


print('The Current Totals are:')
time.sleep(0.9)
print("William:  ", will)
time.sleep(0.4)
print("Henna:    ", henna)
time.sleep(0.4)
print("Miilo:    ", miilo)
time.sleep(0.4)
print("Aimi:     ", aimi)
time.sleep(0.4)
print("   ", recent, "films for other direct reasons.")
time.sleep(0.4)
print("   and" , recent, "films as new releases.")
time.sleep(0.9)
print(' ')
print(' ')
print('   You have watched', total, 'films as a family.')
time.sleep(0.9)
print(' ')
print(' ')


#Calculate if someone is five films behind
max = max(will, henna, miilo, aimi)
min = min(will, henna, miilo, aimi)
diff = max-min

if min == henna:
	lag = 'Henna'
elif min == will:
	lag = 'William'
elif min == miilo:
	lag = 'Miilo'
elif min == aimi:
	lag = 'Aimi'
else: lag = '?'



if diff >= 5:
	print(lag, ' is five films behind.')
	time.sleep(0.5)
	print('   Selecting one of ' +lag+ "\'s films")

else:
	print('No-one is five films behind.')
	time.sleep(0.5)
	print('   Removing ' +last+ ' from Randomiser')


## create lists of people and films

fam_list = ['Aimi', 'Miilo', 'William', 'Henna']
film_list = ['first', 'second', 'third', 'forth']

## Randomly select a family member

if diff >= 5:
	Selector = lag

else:
	fam_list.remove(last)
	Selector = rm.choice(fam_list)


Film = rm.choice(film_list)

## print the selection
time.sleep(0.9)
print ()
print("The family film this week is...")
print ()
time.sleep(2)
print(Selector + "\'s choice!")
 
 
## import the list of films and identify the selections film name to add to output?

reader = csv.DictReader(open('family_film_options.csv'))
famfilm_dict = next(reader)

Choice = Selector + '_' + Film
print ()
time.sleep(2)
print("   " + famfilm_dict[Choice])
print('')

## Add this weeks choice to the list of films watched

Name = famfilm_dict[Choice]
Chooser = Selector
Date = date.today().strftime("%d.%m.%Y")

new_choice = (Name, Chooser, Date)

with open('watched_films.csv', mode='a') as wf:
	writer=csv.writer(wf)
	writer.writerow(" ")
	writer.writerow(new_choice)