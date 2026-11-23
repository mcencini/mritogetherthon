# libbetokan.a for TORTOISE, from FSL's bet2 source (ok3.cpp), built against
# an FSL conda environment: fsl-bet2 brings the shared libraries it calls
# (fsl-meshclass, fsl-newimage, fsl-miscmaths, fsl-newnifti, fsl-cprob,
# fsl-utils, fsl-znzlib) with their headers, and fsl-armawrap, needed only
# to build, the armadillo headers newimage includes.
#
#   make FSLDIR=/opt/fsl                                  # libbetokan.a
#   make FSLDIR=/opt/fsl CXXFLAGS='-O2 -fsigned-char'     # on arm64
#   make -s FSLDIR=/opt/fsl ldflags                       # flags to link it
#
# The archive holds only mainokan. A program linking it adds $(LDLIBS) after
# it, and runs with $(FSLDIR)/lib on its run path. The libraries are named by
# path, not with -L$(FSLDIR)/lib, so that the program's other libraries (zlib,
# libstdc++) still come from the system at link time. In TORTOISE's
# TORTOISEV4/CMakeLists.txt that is, for TORTOISEProcess, DRBUDDI and
# CreateMask:
#   .../external_libraries/bet/Linux/libbetokan.a -lz
# becoming
#   .../external_libraries/bet/Linux/libbetokan.a <make ldflags> -lz

FSLDIR   ?= /opt/fsl
CXXFLAGS ?= -O2
override CXXFLAGS += -std=c++17 -fPIC -pthread -I$(FSLDIR)/include

FSLLIBS = meshclass newimage miscmaths NewNifti cprob utils znz
LDLIBS  = $(FSLLIBS:%=$(FSLDIR)/lib/libfsl-%.so) \
          -Wl,-rpath-link,$(FSLDIR)/lib -Wl,-rpath,$(FSLDIR)/lib -pthread

libbetokan.a: ok3.o
	$(AR) rcs $@ $^

ok3.o: ok3.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

ldflags:
	@echo $(LDLIBS)

clean:
	rm -f ok3.o libbetokan.a

.PHONY: ldflags clean
