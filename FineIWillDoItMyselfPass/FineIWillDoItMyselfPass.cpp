// Wenxuan Shi <wenxuan.shi@northwestern.edu>
// 2024, Northwestern University. All rights reserved.

// this is a function pass that will call the `__cyg_profile_func_enter_fine_i_will_do_it_myself` function at the beginning of each function

#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/Module.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include <llvm/IR/PassManager.h>
#include <llvm/Passes/OptimizationLevel.h>
#include <llvm/Support/Compiler.h>

using namespace llvm;

class FineIWillDoItMyselfPass : public PassInfoMixin<FineIWillDoItMyselfPass> {
public:
    static char ID;
    explicit FineIWillDoItMyselfPass() { }
    static bool isRequired() { return true; }

    PreservedAnalyses run(Module& M, ModuleAnalysisManager& AM)
    {

        FunctionCallee hookFunc = M.getOrInsertFunction(
            "__cyg_profile_func_enter_fine_i_will_do_it_myself",
            FunctionType::get(Type::getVoidTy(M.getContext()), false));

        for (auto& F : M.functions()) {
            if (F.isDeclaration() || F.empty())
                continue;
            IRBuilder<> Builder(&*F.getEntryBlock().getFirstInsertionPt());
            Builder.CreateCall(hookFunc);

        }

        return PreservedAnalyses::all();
    };
};

extern "C" ::llvm::PassPluginLibraryInfo LLVM_ATTRIBUTE_WEAK
llvmGetPassPluginInfo()
{
    return {
        LLVM_PLUGIN_API_VERSION, "FineIWillDoItMyselfPass", LLVM_VERSION_STRING,
        [](PassBuilder& PB) {
            PB.registerOptimizerLastEPCallback([](ModulePassManager& MPM, OptimizationLevel Level) {
                MPM.addPass(FineIWillDoItMyselfPass());
            });
        }
    };
}