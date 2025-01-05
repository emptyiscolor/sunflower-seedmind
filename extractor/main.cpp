#include "extractor.hpp"
#include <algorithm>
#include <iostream>

int main(int argc, char **argv) {
  if (argc < 3) {
    std::cerr
        << "Usage:\n"
        << "  " << argv[0]
        << " <source-file> <function-name> [<compdb-path>] [<extra-args>...]\n"
        << "  or\n"
        << "  " << argv[0]
        << " <source-file> <line-number> [<compdb-path>] [<extra-args>...]\n";
    return 1;
  }

  try {
    // Parse command line arguments
    std::filesystem::path filePath{argv[1]};
    std::string identifier{argv[2]};

    std::optional<std::filesystem::path> databasePath;
    std::vector<std::string> extraArgs;

    if (argc >= 4) {
      std::filesystem::path possibleDbPath{argv[3]};
      if (std::filesystem::exists(possibleDbPath / "compile_commands.json")) {
        databasePath = possibleDbPath;
        extraArgs.assign(argv + 4, argv + argc);
      } else {
        extraArgs.assign(argv + 3, argv + argc);
      }
    }

    // Create extractor
    extractor::Extractor extractor(filePath, extraArgs, databasePath);

    // Determine if we're looking up by line number or function name
    std::optional<extractor::SourceLines> result;
    if (std::all_of(identifier.begin(), identifier.end(), ::isdigit)) {
      result = extractor.extractFunctionByLineNumber(std::stoul(identifier));
    } else {
      result = extractor.extractFunctionByName(identifier);
    }

    // Print results
    if (result) {
      for (const auto &line : *result) {
        std::cout << line.content << '\n';
      }
    } else {
      std::cerr << "No function found.\n";
      return 1;
    }

  } catch (const std::exception &ex) {
    std::cerr << "Error: " << ex.what() << '\n';
    return 1;
  }

  return 0;
}