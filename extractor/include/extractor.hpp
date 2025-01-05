#pragma once

#include "types.hpp"
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace extractor {

class Extractor {
public:
  /**
   * Creates an Extractor instance.
   * @param filePath Path to the source file to analyze
   * @param extraArgs Additional compilation arguments
   * @param databasePath Optional path to compilation database
   * @throws std::runtime_error if initialization fails
   */
  explicit Extractor(
      std::filesystem::path filePath, std::vector<std::string> extraArgs = {},
      std::optional<std::filesystem::path> databasePath = std::nullopt);

  ~Extractor();

  // Prevent copying
  Extractor(const Extractor &) = delete;
  Extractor &operator=(const Extractor &) = delete;

  // Allow moving
  Extractor(Extractor &&) noexcept;
  Extractor &operator=(Extractor &&) noexcept;

  /**
   * Extract function definition by function name.
   * @param funcName Name of the function to extract
   * @return Optional vector of source lines if function is found
   */
  std::optional<SourceLines>
  extractFunctionByName(std::string_view funcName) const;

  /**
   * Extract function definition by line number.
   * @param lineNumber Line number where the function is located
   * @return Optional vector of source lines if function is found
   */
  std::optional<SourceLines>
  extractFunctionByLineNumber(unsigned lineNumber) const;

private:
  class Impl;
  std::unique_ptr<Impl> pImpl; // PIMPL idiom
};

} // namespace extractor