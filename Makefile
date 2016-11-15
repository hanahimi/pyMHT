#OS := $(shell uname)
CPLEX := $(shell command -v cplex -f 2> /dev/null)

ifeq ($(shell uname),Darwin)
#Run macOS commands
init:
	echo "macOS"
	sudo -H pip3 install --upgrade pip
	sudo -H pip3 install -r requirements.txt
	brew install homebrew/science/glpk
	sudo python3 setup.py install
	if [ ! -d $("pulp/") ]; \
	then git clone https://github.com/erikliland/pulp.git ; \
	else git -C pulp/ pull ; \
	fi;
	sudo python3 pulp/setup.py install
	if [ ! -d $("solvers/") ]; \
	then	brew install wget ; \
			wget -r -np -R *html,index.* -nH --cut-dirs=2 http://folk.ntnu.no/eriklil/mac/solvers/ ; \
	fi;

ifndef CPLEX
	brew cask install java
	sudo chmod +x solvers/cplex*
	sudo ./solvers/cplex*
endif
	#if [ ! -d $("Applications/Gurobi*")]; \
	#then $(shell sudo installer -pkg solvers/gurobi* -target /); \
	#fi;
endif


CPLEX := $(shell command -v cplex -f 2> /dev/null)

ifeq ($(shell uname),Linux)
#Run Linux commands
init:
	echo "Linux"
	sudo apt-get update
	sudo apt-get upgrade
	sudo apt-get install python3-setuptools
	sudo easy_install3 pip
	sudo apt-get install python3-tk
	sudo apt-get install python-glpk
	sudo apt-get install glpk-utils
	sudo -H pip install -r requirements.txt
	if [ ! -d $("pulp/") ]; \
	then git clone https://github.com/erikliland/pulp.git ; \
	else git -C pulp/ pull ; \
	fi;
	sudo python3 pulp/setup.py install
	if [ ! -d $("solvers/") ]; \
	then 	sudo apt-get install wget; \
			wget -nc -r -np -R *html,index.* -nH --cut-dirs=2 http://folk.ntnu.no/eriklil/linux/solvers/ ; \
	fi;
ifndef CPLEX
	sudo apt-get install default-jre
	sudo apt-get install default-jdk
	chmod +x solvers/cplex*
	sudo ./solvers/cplex*
	#sudo ln -s /opt/ibm/ILOG/CPLEX_Studio1263/cplex/bin/x86-64_linux/cplex /usr/bin/cplex
endif
	sudo chmod  +x solvers/gurobi*
	sudo tar xvfz solvers/gurobi* -C /opt/
	sudo cp gurobiVars.sh /etc/profile.d/
endif
