 

 this project once complete should provide a simple local api like service for keeping track of all my dev projects across different paths and obsidian vaults.

 the data service will involve two clients, one in python and one go which can query a local sqlite db

while we could write this to be a system that directly reads the project dir data every time its requested from the 'front end', having it unified in a sqlite db gives us an easy access/control point for later. it also means that we can easily predefine queries without too much hassle if need to change them later


