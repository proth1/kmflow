using KMFlowAgent.PII;
using Xunit;

namespace KMFlowAgent.Tests.PII;

public class PrivateBrowsingDetectorTests
{
    private readonly PrivateBrowsingDetector _detector = new();

    [Theory]
    [InlineData("chrome.exe", "Gmail - Incognito", true)]
    [InlineData("chrome.exe", "Gmail - Google Chrome", false)]
    [InlineData("msedge.exe", "Bing - InPrivate", true)]
    [InlineData("msedge.exe", "Bing - Microsoft Edge", false)]
    [InlineData("firefox.exe", "Mozilla Firefox (Private Browsing)", true)]
    [InlineData("firefox.exe", "Mozilla Firefox", false)]
    [InlineData("brave.exe", "Brave Private Tab", true)]
    [InlineData("brave.exe", "Brave Browser", false)]
    [InlineData("vivaldi.exe", "Vivaldi Private Browsing", true)]
    [InlineData("vivaldi.exe", "Vivaldi", false)]
    [InlineData("opera.exe", "Opera Private Window", true)]
    [InlineData("opera.exe", "Opera", false)]
    public void Detects_Private_Browsing(string processId, string title, bool expected)
    {
        Assert.Equal(expected, _detector.IsPrivateBrowsing(processId, title));
    }

    [Fact]
    public void Null_Title_Returns_False()
    {
        Assert.False(_detector.IsPrivateBrowsing("chrome.exe", null));
    }

    [Fact]
    public void Null_Process_Returns_False()
    {
        Assert.False(_detector.IsPrivateBrowsing(null, "Some Title - Incognito"));
    }

    [Fact]
    public void Unknown_Browser_Returns_False()
    {
        Assert.False(_detector.IsPrivateBrowsing("notepad.exe", "Incognito"));
    }
}
