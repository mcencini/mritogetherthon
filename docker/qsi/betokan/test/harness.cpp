// Calls mainokan exactly as TORTOISE's betokan() does (betokan.h), on a volume
// given as a text header "nx ny nz dx dy dz" and raw float32 data, x fastest;
// writes the output buffer as raw float32.
//   harness <in.txt> <in.raw> <out.raw>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <vector>

int mainokan(int argc, char *argv[]);

int main(int argc, char **argv)
{
    if (argc != 4) { std::cerr << "usage: harness in.txt in.raw out.raw\n"; return 2; }
    int sizes[3];
    float res[3];
    std::ifstream hdr(argv[1]);
    hdr >> sizes[0] >> sizes[1] >> sizes[2] >> res[0] >> res[1] >> res[2];
    if (!hdr) { std::cerr << "bad header " << argv[1] << "\n"; return 1; }
    const size_t n = (size_t) sizes[0] * sizes[1] * sizes[2];

    std::vector<float> img(n);
    std::ifstream raw(argv[2], std::ios::binary);
    if (!raw.read((char *) img.data(), n * sizeof(float))) { std::cerr << "short " << argv[2] << "\n"; return 1; }

    // TORTOISE leaves its buffer uninitialised; a sentinel shows voxels that
    // mainokan does not write.
    std::vector<float> mask(n, -7.f);

    char *args[7] = {0};
    args[0] = (char *) sizes;
    args[1] = (char *) res;
    args[2] = (char *) img.data();
    args[3] = (char *) mask.data();
    char p1[3] = "-f";
    float p2 = 0.3;
    args[4] = p1;
    args[5] = (char *) &p2;
    char p3[3] = "-v";
    args[6] = p3;
    int ret = mainokan(7, args);
    std::cout << "mainokan returned " << ret << std::endl;

    std::ofstream out(argv[3], std::ios::binary);
    out.write((const char *) mask.data(), n * sizeof(float));
    return out ? 0 : 1;
}
