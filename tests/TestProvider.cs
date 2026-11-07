using System.Collections.Generic;
using System.Threading.Tasks;
using CoreSelfTests;

namespace MidtownMadness2.Tests {
    public class TestProvider : ICoreTestProvider {
        public IReadOnlyList<CoreTestSuiteInfo> suites { get; } = new[] {
            new CoreTestSuiteInfo {
                name = "api",
                focuses = new[] { "bridges", "customElements", "instMesh", "heightmapScale", "independentPoints", "unicode", "listLabels", "mapLabels", "races", "arrows", "trafficLanes", "meshTextures", "meshPreviews", "projection", "customElementPresets", "trains", "boats", "splines", "rails", "menus", "propPlacers", "parkedCar", "splineState", "incremental", "creation", "roads", "dependencies", "meshSelection", "meshBenchmark" }
            },
            new CoreTestSuiteInfo {
                name = "undo",
                modes = new[] { "new", "props", "ui", "split", "load", "drag", "dropdown", "selection", "placement", "height", "rotation", "guide" },
                existingCityModes = new[] { "props", "ui", "load", "selection" }
            }
        };

        public Task RunAsync(CoreTestContext context) => context.suite == "api"
            ? new Api.ApiSelfTest(context).RunAsync()
            : new History.UndoSelfTest(context).RunAsync();
    }
}
