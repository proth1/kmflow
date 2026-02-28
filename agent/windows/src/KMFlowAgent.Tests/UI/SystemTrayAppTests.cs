// Unit tests for SystemTrayApp view model logic.

using KMFlowAgent.UI;
using Xunit;

namespace KMFlowAgent.Tests.UI;

public class SystemTrayAppTests
{
    [Fact]
    public void BuildTooltip_Active_ShowsActiveState()
    {
        var tooltip = SystemTrayApp.BuildTooltip(isPaused: false, eventCount: 1234);

        Assert.Equal("KMFlow Agent - Active (1,234 events captured)", tooltip);
    }

    [Fact]
    public void BuildTooltip_Paused_ShowsPausedState()
    {
        var tooltip = SystemTrayApp.BuildTooltip(isPaused: true, eventCount: 0);

        Assert.Equal("KMFlow Agent - Paused (0 events captured)", tooltip);
    }

    [Fact]
    public void BuildTooltip_LargeCount_FormatsWithCommas()
    {
        var tooltip = SystemTrayApp.BuildTooltip(isPaused: false, eventCount: 1_000_000);

        Assert.Contains("1,000,000", tooltip);
    }

    [Fact]
    public void GetPauseResumeLabel_NotPaused_ShowsPause()
    {
        Assert.Equal("Pause Capture", SystemTrayApp.GetPauseResumeLabel(isPaused: false));
    }

    [Fact]
    public void GetPauseResumeLabel_Paused_ShowsResume()
    {
        Assert.Equal("Resume Capture", SystemTrayApp.GetPauseResumeLabel(isPaused: true));
    }
}
