#pragma once

#include <string>
#include <vector>

namespace extractor {

/// A line of source code associated with its line number.
struct SourceLine {
  unsigned lineNumber;
  std::string content;
};

using SourceLines = std::vector<SourceLine>;

} // namespace extractor