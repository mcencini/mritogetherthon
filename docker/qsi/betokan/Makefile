# libbetokan.a for TORTOISE, from FSL's bet2 source (ok3.cpp), built against
# an FSL conda environment whose headers and shared libraries it uses:
#   fsl-bet2 (pulls fsl-meshclass, fsl-newimage, fsl-miscmaths, fsl-utils,
#   fsl-znzlib, fsl-cprob) and fsl-armawrap, whose headers newimage needs.
#
#   make FSLDIR=/opt/fsl                       # libbetokan.a
#   make FSLDIR=/opt/fsl CXXFLAGS='-O2 -fsigned-char'
#   make -s FSLDIR=/opt/fsl ldflags            # what a program linking it adds
#
# The archive holds only mainokan; a program linking it adds $(LDLIBS) after
# it, and runs with $(FSLDIR)/lib on its run path.

FSLDIR   ?= /opt/fsl
CXX      ?= g++
CXXFLAGS ?= -O2
override CXXFLAGS += -std=c++17 -fPIC -pthread -I$(FSLDIR)/include

LDLIBS = -L$(FSLDIR)/lib -Wl,-rpath,$(FSLDIR)/lib \
         -lfsl-meshclass -lfsl-newimage -lfsl-miscmaths -lfsl-NewNifti \
         -lfsl-cprob -lfsl-utils -lfsl-znz -pthread

libbetokan.a: ok3.o
	$(AR) rcs $@ $^

ok3.o: ok3.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

ldflags:
	@echo $(LDLIBS)

clean:
	rm -f ok3.o libbetokan.a

.PHONY: ldflags clean
