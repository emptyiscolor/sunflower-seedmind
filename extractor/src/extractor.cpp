#include "extractor.hpp"

#include <clang-c/CXCompilationDatabase.h>
#include <clang-c/Index.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace extractor {
namespace {

/// Helper to convert a CXString to a std::string
std::string toStdString(const CXString &cxstr) {
  const char *cstr = clang_getCString(cxstr);
  std::string result = (cstr ? cstr : "");
  clang_disposeString(cxstr);
  return result;
}

} // anonymous namespace

//---------------------------------------------------------------------
// Extractor::Impl
//---------------------------------------------------------------------
class Extractor::Impl {
public:
  Impl(const std::filesystem::path &filePath,
       const std::vector<std::string> &extraArgs,
       const std::optional<std::filesystem::path> &databasePath)
      : mIndex(clang_createIndex(0, 0)) {
    if (!std::filesystem::exists(filePath)) {
      throw std::runtime_error("Source file not found: " + filePath.string());
    }

    // Convert paths to strings for libclang.
    std::string filePathStr = filePath.string();
    std::optional<std::string> dbPathStr =
        databasePath.has_value() ? std::make_optional(databasePath->string())
                                 : std::nullopt;

    mTranslationUnit = createTranslationUnit(filePathStr, extraArgs, dbPathStr);
  }

  ~Impl() {
    if (mTranslationUnit) {
      clang_disposeTranslationUnit(mTranslationUnit);
    }
    if (mIndex) {
      clang_disposeIndex(mIndex);
    }
  }

  // Disable copying
  Impl(const Impl &) = delete;
  Impl &operator=(const Impl &) = delete;

  // Implement extraction logic
  std::optional<SourceLines>
  extractFunctionByName(std::string_view funcName) const {
    CXCursor rootCursor = clang_getTranslationUnitCursor(mTranslationUnit);
    CXCursor funcCursor =
        findFunctionDefinitionByName(rootCursor, std::string(funcName));
    if (clang_Cursor_isNull(funcCursor)) {
      // Not found
      return std::nullopt;
    }
    auto lines = extractNodeSource(funcCursor);
    if (lines.empty()) {
      return std::nullopt;
    }
    return lines;
  }

  std::optional<SourceLines>
  extractFunctionByLineNumber(unsigned lineNumber) const {
    CXCursor rootCursor = clang_getTranslationUnitCursor(mTranslationUnit);
    CXCursor funcCursor =
        findFunctionDefinitionByLineNumber(rootCursor, lineNumber);
    if (clang_Cursor_isNull(funcCursor)) {
      // Not found
      return std::nullopt;
    }
    auto lines = extractNodeSource(funcCursor);
    if (lines.empty()) {
      return std::nullopt;
    }
    return lines;
  }

private:
  CXIndex mIndex{nullptr};
  CXTranslationUnit mTranslationUnit{nullptr};

private:
  // ---------------------------------------------------------
  // Private methods
  // ---------------------------------------------------------

  /**
   * Create a translation unit for the given file.
   * - The `extraArgs` parameter allows additional compile flags like `-I
   * /some/include`.
   * - The `databasePath` can be empty or a path to a compile_commands.json
   * directory.
   */
  CXTranslationUnit
  createTranslationUnit(const std::string &filePath,
                        const std::vector<std::string> &extraArgs,
                        const std::optional<std::string> &databasePath) {
    // Build our argument list
    std::vector<const char *> clangArgs;
    // Force C++ parsing with at least C++11
    clangArgs.push_back("-x");
    clangArgs.push_back("c++");
    clangArgs.push_back("-std=c++11");

    // If a compilation database path is provided, gather the -D macros from it
    if (databasePath.has_value()) {
      auto dbArgs = getCompileArgs(filePath, databasePath.value());
      for (auto &darg : dbArgs) {
        clangArgs.push_back(darg.c_str());
      }
    }

    // Add any extra arguments
    for (auto &arg : extraArgs) {
      clangArgs.push_back(arg.c_str());
    }

    // Create the translation unit
    CXTranslationUnit tu = clang_parseTranslationUnit(
        mIndex, filePath.c_str(), clangArgs.data(),
        static_cast<int>(clangArgs.size()), nullptr, 0, CXTranslationUnit_None);

    if (!tu) {
      throw std::runtime_error("Unable to parse the source file: " + filePath);
    }

    return tu;
  }

  /**
   * Recursively find the function definition by name in the AST.
   */
  static CXCursor findFunctionDefinitionByName(CXCursor cursor,
                                               const std::string &funcName) {
    // If the current cursor is a function/method definition with matching
    // spelling
    if ((clang_getCursorKind(cursor) == CXCursor_FunctionDecl ||
         clang_getCursorKind(cursor) == CXCursor_CXXMethod) &&
        clang_isCursorDefinition(cursor)) {
      std::string spelling = toStdString(clang_getCursorSpelling(cursor));
      if (spelling == funcName) {
        return cursor;
      }
    }

    // Prepare search data
    struct FindFunctionByNameData {
      std::string funcName;
      CXCursor foundCursor;
    } data{funcName, clang_getNullCursor()};

    // Recurse into children
    clang_visitChildren(
        cursor,
        [](CXCursor c, CXCursor /*parent*/, CXClientData clientData) {
          auto *searchData =
              reinterpret_cast<FindFunctionByNameData *>(clientData);
          CXCursor found =
              findFunctionDefinitionByName(c, searchData->funcName);
          if (!clang_Cursor_isNull(found)) {
            searchData->foundCursor = found;
            return CXChildVisit_Break;
          }
          return CXChildVisit_Continue;
        },
        &data);

    return data.foundCursor;
  }

  /**
   * Recursively find the function definition by line number in the AST.
   * Note: This is a simplified approach that checks if the node's extent covers
   * the given line.
   */
  static CXCursor findFunctionDefinitionByLineNumber(CXCursor cursor,
                                                     unsigned lineNumber) {
    // Retrieve the source range
    CXSourceRange range = clang_getCursorExtent(cursor);
    CXSourceLocation startLoc = clang_getRangeStart(range);
    CXSourceLocation endLoc = clang_getRangeEnd(range);

    unsigned startLine = 0, startColumn = 0;
    clang_getSpellingLocation(startLoc, nullptr, &startLine, &startColumn,
                              nullptr);

    unsigned endLine = 0, endColumn = 0;
    clang_getSpellingLocation(endLoc, nullptr, &endLine, &endColumn, nullptr);

    // Check if the cursor covers the requested line
    if (startLine <= lineNumber && lineNumber <= endLine) {
      // Check if the node is a function or method definition
      if ((clang_getCursorKind(cursor) == CXCursor_FunctionDecl ||
           clang_getCursorKind(cursor) == CXCursor_CXXMethod) &&
          clang_isCursorDefinition(cursor)) {
        return cursor;
      }
    }

    // Prepare search data
    struct FindFunctionByLineData {
      unsigned lineNumber;
      CXCursor foundCursor;
    } data{lineNumber, clang_getNullCursor()};

    // Recurse into children
    clang_visitChildren(
        cursor,
        [](CXCursor c, CXCursor /*parent*/, CXClientData clientData) {
          auto *lineData =
              reinterpret_cast<FindFunctionByLineData *>(clientData);
          CXCursor found =
              findFunctionDefinitionByLineNumber(c, lineData->lineNumber);
          if (!clang_Cursor_isNull(found)) {
            lineData->foundCursor = found;
            return CXChildVisit_Break;
          }
          return CXChildVisit_Continue;
        },
        &data);

    return data.foundCursor;
  }

  /**
   * Extract the source code lines from the given cursor's extent.
   */
  static SourceLines extractNodeSource(CXCursor cursor) {
    // Get the range for the cursor
    CXSourceRange range = clang_getCursorExtent(cursor);
    CXSourceLocation startLoc = clang_getRangeStart(range);
    CXSourceLocation endLoc = clang_getRangeEnd(range);

    CXFile file;
    unsigned startLine = 0, startColumn = 0;
    unsigned endLine = 0, endColumn = 0;

    clang_getSpellingLocation(startLoc, &file, &startLine, &startColumn,
                              nullptr);
    clang_getSpellingLocation(endLoc, nullptr, &endLine, &endColumn, nullptr);

    // Convert CXFile to path
    std::string filename = toStdString(clang_getFileName(file));
    if (filename.empty()) {
      return {};
    }

    // Read the file lines
    std::ifstream ifs(filename);
    if (!ifs.is_open()) {
      std::cerr << "Failed to open file: " << filename << std::endl;
      return {};
    }

    std::vector<std::string> allLines;
    {
      std::string line;
      while (std::getline(ifs, line)) {
        allLines.push_back(line);
      }
    }

    // Extract the relevant lines
    SourceLines result;
    if (startLine <= allLines.size()) {
      for (unsigned i = startLine; i <= endLine && i <= allLines.size(); ++i) {
        // Note: i - 1 index in allLines
        result.push_back({i, allLines[i - 1]});
      }
    }
    return result;
  }

  /**
   * Get the compile arguments from the compilation database (optional).
   * This is simplified: we only keep arguments that start with "-D" for macros.
   */
  static std::vector<std::string>
  getCompileArgs(const std::string &filePath, const std::string &databasePath) {
    if (!std::filesystem::exists(databasePath)) {
      throw std::runtime_error("Compilation database " + databasePath +
                               " not found.");
    }

    CXCompilationDatabase_Error error;
    CXCompilationDatabase compdb =
        clang_CompilationDatabase_fromDirectory(databasePath.c_str(), &error);
    if (error != CXCompilationDatabase_NoError) {
      throw std::runtime_error("Failed to load compilation database from: " +
                               databasePath);
    }

    // Retrieve compile commands for this file
    CXCompileCommands commands =
        clang_CompilationDatabase_getCompileCommands(compdb, filePath.c_str());
    if (!commands) {
      clang_CompilationDatabase_dispose(compdb);
      std::cerr << "[!] No compile commands found for file: " << filePath
                << std::endl;
      return {};
    }

    unsigned numCommands = clang_CompileCommands_getSize(commands);
    std::vector<std::string> compileArgs;
    for (unsigned i = 0; i < numCommands; i++) {
      CXCompileCommand cmd = clang_CompileCommands_getCommand(commands, i);
      unsigned numArgs = clang_CompileCommand_getNumArgs(cmd);
      for (unsigned j = 0; j < numArgs; j++) {
        CXString argStr = clang_CompileCommand_getArg(cmd, j);
        std::string arg = toStdString(argStr);
        // Keep only macros for simplicity
        if (!arg.empty() && arg.rfind("-D", 0) == 0) {
          compileArgs.push_back(arg);
        }
      }
    }

    // Clean up
    clang_CompileCommands_dispose(commands);
    clang_CompilationDatabase_dispose(compdb);

    return compileArgs;
  }
};

//---------------------------------------------------------------------
// Extractor (public API) methods
//---------------------------------------------------------------------
Extractor::Extractor(std::filesystem::path filePath,
                     std::vector<std::string> extraArgs,
                     std::optional<std::filesystem::path> databasePath)
    : pImpl(std::make_unique<Impl>(std::move(filePath), std::move(extraArgs),
                                   std::move(databasePath))) {}

Extractor::~Extractor() = default;

Extractor::Extractor(Extractor &&) noexcept = default;
Extractor &Extractor::operator=(Extractor &&) noexcept = default;

std::optional<SourceLines>
Extractor::extractFunctionByName(std::string_view funcName) const {
  return pImpl->extractFunctionByName(funcName);
}

std::optional<SourceLines>
Extractor::extractFunctionByLineNumber(unsigned lineNumber) const {
  return pImpl->extractFunctionByLineNumber(lineNumber);
}

} // namespace extractor
