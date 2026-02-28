using KMFlowAgent.IPC;
using KMFlowAgent.PII;
using Xunit;

namespace KMFlowAgent.Tests.PII;

public class CaptureContextFilterTests
{
    [Theory]
    [InlineData("1Password.exe")]
    [InlineData("LastPass.exe")]
    [InlineData("Bitwarden.exe")]
    [InlineData("KeePass.exe")]
    [InlineData("KeePassXC.exe")]
    [InlineData("SecurityHealthHost.exe")]
    [InlineData("CredentialUIBroker.exe")]
    public void Hardcoded_Blocklist_Blocks_Password_Managers(string processName)
    {
        var filter = new CaptureContextFilter();

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.KeyboardAction,
            sequenceNumber: 1,
            bundleIdentifier: processName);

        Assert.True(filter.ShouldBlock(evt));
    }

    [Fact]
    public void Null_Process_Identifier_Is_Blocked()
    {
        var filter = new CaptureContextFilter();

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.KeyboardAction,
            sequenceNumber: 1,
            bundleIdentifier: null);

        Assert.True(filter.ShouldBlock(evt));
    }

    [Fact]
    public void Known_Safe_App_Is_Not_Blocked()
    {
        var filter = new CaptureContextFilter();

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.KeyboardAction,
            sequenceNumber: 1,
            bundleIdentifier: "EXCEL.EXE");

        Assert.False(filter.ShouldBlock(evt));
    }

    [Fact]
    public void Allowlist_Blocks_Non_Listed_Apps()
    {
        var filter = new CaptureContextFilter(
            allowlist: new[] { "EXCEL.EXE", "CHROME.EXE" });

        var blockedEvt = CaptureEvent.Create(
            eventType: DesktopEventType.KeyboardAction,
            sequenceNumber: 1,
            bundleIdentifier: "NOTEPAD.EXE");

        var allowedEvt = CaptureEvent.Create(
            eventType: DesktopEventType.KeyboardAction,
            sequenceNumber: 2,
            bundleIdentifier: "EXCEL.EXE");

        Assert.True(filter.ShouldBlock(blockedEvt));
        Assert.False(filter.ShouldBlock(allowedEvt));
    }

    [Fact]
    public void Url_Event_Blocked_In_Private_Browsing()
    {
        var filter = new CaptureContextFilter();

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.UrlNavigation,
            sequenceNumber: 1,
            bundleIdentifier: "CHROME.EXE",
            windowTitle: "Google - Incognito");

        Assert.True(filter.ShouldBlock(evt));
    }

    [Fact]
    public void Url_Event_Allowed_In_Normal_Browsing()
    {
        var filter = new CaptureContextFilter();

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.UrlNavigation,
            sequenceNumber: 1,
            bundleIdentifier: "CHROME.EXE",
            windowTitle: "Google - Google Chrome");

        Assert.False(filter.ShouldBlock(evt));
    }

    [Fact]
    public void Blocklist_Is_Case_Insensitive()
    {
        var filter = new CaptureContextFilter();

        Assert.True(filter.IsBlockedProcess("keepass.exe"));
        Assert.True(filter.IsBlockedProcess("KEEPASS.EXE"));
        Assert.True(filter.IsBlockedProcess("KeePass.exe"));
    }
}
